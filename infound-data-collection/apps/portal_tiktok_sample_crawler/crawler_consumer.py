import asyncio
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import quote_plus

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from common.core.config import get_settings
from common.core.exceptions import MessageProcessingError, NonRetryableMessageError
from common.core.logger import get_logger
from common.mq.connection import RabbitMQConnection
from common.mq.consumer_base import ConsumerBase
from structlog import contextvars as struct_contextvars
from .services.crawler_runner_service import CrawlerRunnerService

settings = get_settings()
logger = get_logger()


def _parse_message_body(body_bytes: bytes) -> Dict[str, Any]:
    try:
        return json.loads(body_bytes.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Failed to parse message body: {exc}") from exc


def _normalize_tabs(body: Dict[str, Any]) -> List[str]:
    raw = None
    if isinstance(body.get("tabs"), list):
        raw = body.get("tabs")
    else:
        tab = body.get("tab") or body.get("tabName")
        raw = [tab] if tab is not None else []
    return [str(item).strip().lower() for item in raw if item is not None and str(item).strip()]


async def _publish_to_dead_letter(
    conn: RabbitMQConnection,
    *,
    body: bytes,
    message_id: Optional[str],
    reason: str,
) -> None:
    try:
        dlx_exchange = getattr(conn, "dlx_exchange", None)
        if not dlx_exchange:
            return
        headers = {"x-error": reason}
        if message_id:
            headers["x-original-message-id"] = message_id
        await dlx_exchange.publish(
            aio_pika.Message(
                body=body,
                message_id=message_id,
                headers=headers,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=conn.dl_routing_key,
        )
    except Exception:
        logger.warning("Failed to publish to dead-letter exchange", exc_info=True)


def _enforce_queue_tabs(kind: str, body: Dict[str, Any]) -> Dict[str, Any]:
    tabs = _normalize_tabs(body)
    if kind == "completed":
        if not tabs:
            body = dict(body)
            body["tabs"] = ["completed"]
            return body
        if not (len(tabs) == 1 and tabs[0] == "completed"):
            raise NonRetryableMessageError(
                f"completed queue only accepts tabs=['completed'], got: {tabs!r}"
            )
        return body
    if len(tabs) == 1 and tabs[0] == "completed":
        raise NonRetryableMessageError("other queue does not accept tabs=['completed']")
    return body


class SampleCrawlerConsumer(ConsumerBase):
    """样品爬虫核心逻辑（共享 Playwright 会话池）"""

    def __init__(self):
        amqp_url = (
            f"amqp://{quote_plus(settings.RABBITMQ_USERNAME)}:"
            f"{quote_plus(settings.RABBITMQ_PASSWORD)}@"
            f"{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}/"
            f"{quote_plus(settings.RABBITMQ_VHOST)}"
        )
        rabbitmq_conn = RabbitMQConnection(
            url=amqp_url,
            exchange_name=settings.RABBITMQ_EXCHANGE_NAME,
            routing_key=settings.RABBITMQ_ROUTING_KEY,
            queue_name=settings.RABBITMQ_QUEUE_NAME,
            at_most_once=getattr(settings, "RABBITMQ_AT_MOST_ONCE", False),
            prefetch_count=settings.RABBITMQ_PREFETCH_COUNT,
            reconnect_delay=settings.RABBITMQ_RECONNECT_DELAY,
            max_reconnect_attempts=settings.RABBITMQ_MAX_RECONNECT_ATTEMPTS,
        )
        super().__init__(rabbitmq_conn)
        # Playwright 会话池：常驻浏览器，优先复用空闲实例，无空闲时才新建。
        self.pool: List[Dict[str, Any]] = []
        self.pool_lock = asyncio.Lock()
        self.default_region = str(getattr(settings, "SAMPLE_DEFAULT_REGION", "MX") or "MX").upper()
        self.pool_min = int(getattr(settings, "SAMPLE_BROWSER_POOL_SIZE", 1) or 1)
        self.account_config_path = Path(
            getattr(settings, "SAMPLE_ACCOUNT_CONFIG_PATH", "configs/accounts.json")
        )
        self.account_catalog = self._load_accounts_catalog()
        enabled_accounts = sum(1 for account in self.account_catalog if account.get("enabled", True))
        configured_pool_max = getattr(settings, "SAMPLE_BROWSER_POOL_MAX", None)
        if configured_pool_max is None:
            base_pool_max = self.pool_min
        else:
            base_pool_max = int(configured_pool_max or self.pool_min)
        self.pool_max = max(base_pool_max, self.pool_min, enabled_accounts or 1)
        self.active_service: Optional[CrawlerRunnerService] = None
        self._pending_accounts: Dict[str, Set[str]] = defaultdict(set)
        self.prewarm_tasks = []
        for _ in range(self.pool_min):
            task = asyncio.create_task(self._spawn_and_add(self.default_region, None))
            task.add_done_callback(self._consume_background_task_result)
            self.prewarm_tasks.append(task)

    @staticmethod
    def _consume_background_task_result(task: asyncio.Task) -> None:
        try:
            task.result()
        except Exception:
            logger.warning("Background task failed", exc_info=True)

    async def _spawn_and_add(self, region: str, account_name: Optional[str]) -> None:
        region_key = str(region or self.default_region or "MX").upper()
        async with self.pool_lock:
            spawn_account, reserved = self._reserve_account_for_spawn(region_key, account_name)
        try:
            slot = await self._spawn_service(region_key, spawn_account)
        except Exception:
            if reserved:
                async with self.pool_lock:
                    self._release_reserved_account(region_key, spawn_account)
            raise
        async with self.pool_lock:
            if reserved:
                self._release_reserved_account(region_key, spawn_account)
            self.pool.append(slot)
            logger.info("预热 Playwright 会话完成", pool_size=len(self.pool))

    async def _spawn_service(self, region: str, account_name: Optional[str]) -> Dict[str, Any]:
        region_key = str(region or self.default_region or "MX").upper()
        svc = CrawlerRunnerService()
        profile = svc.resolve_profile(region=region_key, account_name=account_name)
        await svc.initialize(profile)
        # 仅完成登录，保持在当前页面；真正任务时再跳转 target_url
        logger.info("新建 Playwright 会话并完成登录", login_email=profile.login_email)
        return {"service": svc, "in_use": False}

    async def _acquire_slot(self, region: str, account_name: Optional[str]) -> Dict[str, Any]:
        # 等待预热任务（忽略失败）
        for task in list(self.prewarm_tasks):
            if not task.done():
                try:
                    await task
                except Exception:
                    pass
        resolver = self.pool[0]["service"] if self.pool else CrawlerRunnerService()
        desired_profile = resolver.resolve_profile(region=region, account_name=account_name)
        while True:
            spawn_needed = False
            spawn_account: Optional[str] = None
            spawn_reserved = False
            async with self.pool_lock:
                slot_states: List[Dict[str, Any]] = []
                state_map: Dict[int, Dict[str, Any]] = {}
                for idx, slot in enumerate(self.pool):
                    svc = slot["service"]
                    login_email = (
                        svc.account_profile.login_email
                        if svc.account_profile and svc.account_profile.login_email
                        else None
                    )
                    session_state = svc.describe_session_state()
                    state: Dict[str, Any] = {
                        "slot_index": idx,
                        "in_use": bool(slot["in_use"]),
                        "login_email": login_email,
                        "has_live_session": svc.has_live_session(),
                        "matches_desired": bool(
                            login_email
                            and desired_profile
                            and login_email == desired_profile.login_email
                        ),
                    }
                    state.update(session_state)
                    slot_states.append(state)
                    state_map[id(slot)] = state

                idle = sum(
                    1 for state in slot_states if not state["in_use"] and state["has_live_session"]
                )
                logger.info(
                    "检查会话池",
                    pool_size=len(self.pool),
                    idle=idle,
                    max_size=self.pool_max,
                    slots=slot_states,
                )
                for slot in list(self.pool):
                    svc = slot["service"]
                    slot_state = state_map.get(id(slot), {})
                    if slot["in_use"]:
                        continue
                    if not slot_state.get("has_live_session", svc.has_live_session()):
                        # 清理失效会话，允许后续新建
                        logger.warning(
                            "检测到失效会话，将清理",
                            slot_index=slot_state.get("slot_index"),
                            login_email=slot_state.get("login_email"),
                            session_state=slot_state or svc.describe_session_state(),
                        )
                        try:
                            await svc.close()
                        except Exception:
                            pass
                        try:
                            self.pool.remove(slot)
                        except ValueError:
                            pass
                        continue
                    if not svc.account_profile or svc.account_profile.login_email != desired_profile.login_email:
                        logger.info(
                            "会话账号不匹配，跳过",
                            slot_index=slot_state.get("slot_index"),
                            login_email=slot_state.get("login_email"),
                            desired_login=desired_profile.login_email,
                        )
                        continue
                    slot["in_use"] = True
                    logger.info(
                        "复用常驻会话",
                        pool_size=len(self.pool),
                        idle=idle - 1 if idle else 0,
                        slot_index=slot_state.get("slot_index"),
                        login_email=slot_state.get("login_email"),
                    )
                    return slot
                # 优先重建空闲会话以满足账号要求，尽量不新开浏览器
                for slot in self.pool:
                    if slot["in_use"]:
                        continue
                    try:
                        await slot["service"].initialize(desired_profile)
                        slot["in_use"] = True
                        logger.info(
                            "重建空闲会话并复用",
                            pool_size=len(self.pool),
                            slot_index=state_map.get(id(slot), {}).get("slot_index"),
                            login_email=desired_profile.login_email,
                        )
                        return slot
                    except Exception:
                        logger.warning("空闲会话重建失败，等待其他会话释放", exc_info=True)
                        continue
                # 无法重建且未达上限，才考虑扩容
                if len(self.pool) < self.pool_max:
                    spawn_account, spawn_reserved = self._reserve_account_for_spawn(
                        region, account_name
                    )
                    spawn_needed = True
                # 池已满且重建失败，只能等待空闲
            if spawn_needed:
                try:
                    slot = await self._spawn_service(region, spawn_account)
                except Exception:
                    if spawn_reserved:
                        async with self.pool_lock:
                            self._release_reserved_account(region, spawn_account)
                    raise
                async with self.pool_lock:
                    if spawn_reserved:
                        self._release_reserved_account(region, spawn_account)
                    slot["in_use"] = True
                    self.pool.append(slot)
                    logger.info("扩容 Playwright 会话池", pool_size=len(self.pool))
                    return slot
            await asyncio.sleep(1)

    async def _release_slot(self, slot: Dict[str, Any]) -> None:
        svc: CrawlerRunnerService = slot["service"]
        released = False
        try:
            if svc._main_page and not svc._main_page.is_closed():
                region = svc.account_profile.region if svc.account_profile else None
                # 释放阶段只要执行过跳转 + 等待即可，不依赖首页 DOM 判定（避免 UI 变更导致卡死）
                await asyncio.wait_for(svc._goto_home_soft(svc._main_page, region, wait_ms=5000), timeout=25)
        except asyncio.TimeoutError:
            logger.warning("释放会话回到首页超时，将直接归还会话以便复用")
        except Exception:
            logger.warning("释放会话回到首页失败，将直接归还会话以便复用", exc_info=True)
        async with self.pool_lock:
            if svc._browser:
                slot["in_use"] = False
                released = True
            else:
                try:
                    self.pool.remove(slot)
                except ValueError:
                    pass
        if released:
            try:
                async with self.pool_lock:
                    idle = sum(
                        1
                        for slot_item in self.pool
                        if not slot_item["in_use"] and slot_item["service"].has_live_session()
                    )
                    pool_size = len(self.pool)
                logger.info("会话已释放并归还池子", pool_size=pool_size, idle=idle)
            except Exception:
                logger.info("会话已释放并归还池子")

    async def process_message_body(self, message_id: str, body: Dict[str, Any]) -> None:
        """处理爬虫任务"""
        function_name = str(body.get("function") or "sample").strip().lower()
        if function_name != "sample":
            raise MessageProcessingError(f"Unsupported function '{function_name}', only 'sample' is available")

        campaign_id = body.get("campaign_id") or body.get("campaignId")
        scan_all = bool(
            body.get("scan_all_pages")
            if "scan_all_pages" in body
            else body.get("scanAllPages", False)
        )
        if not campaign_id and not scan_all:
            raise MessageProcessingError(
                "Missing campaign_id; set scan_all_pages=true to crawl entire tab"
            )

        region = str(body.get("region") or self.default_region or "MX").upper()
        account_name = body.get("account_name") or body.get("accountName")
        tabs_meta = (
            body.get("tabs")
            if isinstance(body.get("tabs"), list)
            else [body.get("tab") or body.get("tabName")]
        )
        tabs_label = ",".join([str(tab) for tab in tabs_meta if tab]) if tabs_meta else None
        ctx_values = {
            "message_id": message_id,
            "task_tag": (message_id or "")[:8],
            "campaign_id": campaign_id,
            "region": region,
            "tabs": tabs_label,
        }
        ctx_values = {key: value for key, value in ctx_values.items() if value}
        ctx_keys: Tuple[str, ...] = tuple(ctx_values.keys())
        if ctx_values:
            struct_contextvars.bind_contextvars(**ctx_values)

        logger.info("开始执行 CrawlerConsumer", body=body)

        slot: Optional[Dict[str, Any]] = None
        try:
            slot = await self._acquire_slot(region, account_name)
            service: CrawlerRunnerService = slot["service"]
            service.stop_event.clear()
            self.active_service = service
            try:
                if service.account_profile and not (
                    body.get("account_name") or body.get("accountName")
                ):
                    body = dict(body)
                    body["account_name"] = service.account_profile.name
                    body["accountName"] = service.account_profile.name
                try:
                    await service.process_campaign_task(body)
                except Exception:
                    # 按约定：消息不允许重试，因此此处吞掉异常让上层 ack。
                    logger.error("Crawler task failed; message will be acked (no retry)", exc_info=True)
            finally:
                if self.active_service is service:
                    self.active_service = None
                if slot:
                    await self._release_slot(slot)
        finally:
            if ctx_keys:
                struct_contextvars.unbind_contextvars(*ctx_keys)

        logger.info("结束执行 CrawlerConsumer")


class CrawlerConsumer(SampleCrawlerConsumer):
    """
    样品爬虫（单进程双队列）：
    - completed queue：只处理 tabs=['completed']（未传 tabs 则自动注入）
    - other queue：处理除 completed 以外的 tab
    """

    def __init__(self) -> None:
        super().__init__()
        amqp_url = (
            f"amqp://{quote_plus(settings.RABBITMQ_USERNAME)}:"
            f"{quote_plus(settings.RABBITMQ_PASSWORD)}@"
            f"{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}/"
            f"{quote_plus(settings.RABBITMQ_VHOST)}"
        )
        at_most_once = bool(getattr(settings, "RABBITMQ_AT_MOST_ONCE", False))
        self.completed_conn = RabbitMQConnection(
            url=amqp_url,
            exchange_name=settings.RABBITMQ_EXCHANGE_NAME,
            routing_key=settings.RABBITMQ_COMPLETED_ROUTING_KEY,
            queue_name=settings.RABBITMQ_COMPLETED_QUEUE_NAME,
            at_most_once=at_most_once,
            prefetch_count=settings.RABBITMQ_PREFETCH_COUNT,
            reconnect_delay=settings.RABBITMQ_RECONNECT_DELAY,
            max_reconnect_attempts=settings.RABBITMQ_MAX_RECONNECT_ATTEMPTS,
        )
        self.other_conn = RabbitMQConnection(
            url=amqp_url,
            exchange_name=settings.RABBITMQ_EXCHANGE_NAME,
            routing_key=settings.RABBITMQ_OTHER_ROUTING_KEY,
            queue_name=settings.RABBITMQ_OTHER_QUEUE_NAME,
            at_most_once=at_most_once,
            prefetch_count=settings.RABBITMQ_PREFETCH_COUNT,
            reconnect_delay=settings.RABBITMQ_RECONNECT_DELAY,
            max_reconnect_attempts=settings.RABBITMQ_MAX_RECONNECT_ATTEMPTS,
        )
        self._consume_task_completed: Optional[asyncio.Task] = None
        self._consume_task_other: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self.logger.info(
            "Starting dual-queue sample crawler",
            completed_queue=self.completed_conn.queue_name,
            other_queue=self.other_conn.queue_name,
            at_most_once=bool(getattr(settings, "RABBITMQ_AT_MOST_ONCE", False)),
        )
        self._consume_task_completed = asyncio.create_task(
            self._consume_loop(self.completed_conn, kind="completed")
        )
        self._consume_task_other = asyncio.create_task(
            self._consume_loop(self.other_conn, kind="other")
        )
        await asyncio.gather(self._consume_task_completed, self._consume_task_other)

    async def stop(self) -> None:
        try:
            await super().stop()
        finally:
            await self.completed_conn.close()
            await self.other_conn.close()

    async def _consume_loop(self, conn: RabbitMQConnection, *, kind: str) -> None:
        while True:
            try:
                await conn.connect()
                await conn.queue.consume(
                    lambda msg: self._process_message(kind, conn, msg),
                    no_ack=bool(getattr(conn, "at_most_once", False)),
                )
                self.logger.info(
                    "Consumer binding ready",
                    kind=kind,
                    exchange=conn.exchange_name,
                    routing_key=conn.routing_key,
                    queue=conn.queue_name,
                )
                while True:
                    await asyncio.sleep(1)
            except Exception:
                self.logger.error("Consumer loop error, restarting...", kind=kind, exc_info=True)
                try:
                    await conn.close()
                except Exception:
                    pass
                await asyncio.sleep(conn.reconnect_delay)

    async def _process_message(
        self,
        kind: str,
        conn: RabbitMQConnection,
        message: AbstractIncomingMessage,
    ) -> None:
        message_id = message.message_id
        self.logger.info(
            "Received message",
            kind=kind,
            message_id=message_id,
            routing_key=message.routing_key,
        )

        if getattr(conn, "at_most_once", False):
            await self._process_message_at_most_once(kind, conn, message)
            return

        try:
            body = _parse_message_body(message.body)
            body = _enforce_queue_tabs(kind, body)
            await self.process_message_body(message_id, body)
            await message.ack()
            self.logger.info("Message processed successfully", kind=kind, message_id=message_id)
        except ValueError as exc:
            self.logger.error("Invalid message format", kind=kind, message_id=message_id, error=str(exc))
            await message.reject(requeue=False)
        except NonRetryableMessageError as exc:
            self.logger.error("Non-retryable message error", kind=kind, message_id=message_id, error=str(exc))
            await message.reject(requeue=False)
        except MessageProcessingError as exc:
            self.logger.error(
                "Message processing failed",
                kind=kind,
                message_id=message_id,
                error=str(exc),
                exc_info=True,
            )
            await message.reject(requeue=False)
        except Exception:
            self.logger.critical("Unexpected error processing message", kind=kind, message_id=message_id, exc_info=True)
            await message.reject(requeue=False)

    async def _process_message_at_most_once(
        self,
        kind: str,
        conn: RabbitMQConnection,
        message: AbstractIncomingMessage,
    ) -> None:
        message_id = message.message_id
        try:
            body = _parse_message_body(message.body)
            body = _enforce_queue_tabs(kind, body)
        except Exception as exc:
            self.logger.error(
                "Invalid message (at_most_once; dropping)",
                kind=kind,
                message_id=message_id,
                error=str(exc),
            )
            await _publish_to_dead_letter(conn, body=message.body, message_id=message_id, reason=str(exc))
            return

        try:
            await self.process_message_body(message_id, body)
            self.logger.info("Message processed successfully (at_most_once)", kind=kind, message_id=message_id)
        except Exception as exc:
            self.logger.error(
                "Message processing failed (at_most_once; dropping)",
                kind=kind,
                message_id=message_id,
                error=str(exc),
                exc_info=True,
            )
            await _publish_to_dead_letter(conn, body=message.body, message_id=message_id, reason=str(exc))

    async def stop(self) -> None:
        """关闭所有常驻 Playwright 实例后再停止 MQ 连接。"""
        for task in self.prewarm_tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except Exception:
                    pass
        async with self.pool_lock:
            for slot in list(self.pool):
                try:
                    await slot["service"].close()
                except Exception:
                    pass
            self.pool.clear()
        await super().stop()

    def cancel_current_task(self) -> None:
        """外部调用：请求中断当前任务（未提供消息级接口时的兜底）。"""
        if self.active_service:
            self.active_service.stop_event.set()

    def _load_accounts_catalog(self) -> List[Dict[str, Any]]:
        path = self.account_config_path
        if not path.exists():
            logger.warning("Account config file not found", path=str(path))
            return []
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            accounts = data.get("accounts", [])
            return accounts if isinstance(accounts, list) else []
        except Exception:
            logger.warning("Failed to load account config", path=str(path), exc_info=True)
            return []

    def _reserve_account_for_spawn(
        self, region: str, requested_account_name: Optional[str]
    ) -> Tuple[Optional[str], bool]:
        if requested_account_name:
            return requested_account_name, False

        region_key = str(region or self.default_region or "MX").upper()
        used_names: Set[str] = set()
        for slot in self.pool:
            profile = slot["service"].account_profile
            if not profile or not profile.name:
                continue
            profile_region = str(getattr(profile, "region", "") or "").upper()
            if profile_region != region_key:
                continue
            used_names.add(profile.name)
        used_names.update(self._pending_accounts.get(region_key, set()))

        for account in self.account_catalog:
            if not account.get("enabled", True):
                continue
            account_region = str(account.get("region", "") or "").upper()
            if account_region != region_key:
                continue
            name = str(account.get("name") or "").strip()
            if name and name not in used_names:
                self._pending_accounts[region_key].add(name)
                return name, True
        return None, False

    def _release_reserved_account(self, region: str, account_name: Optional[str]) -> None:
        if not account_name:
            return
        region_key = str(region or self.default_region or "MX").upper()
        pending = self._pending_accounts.get(region_key)
        if not pending:
            return
        pending.discard(account_name)
        if not pending:
            self._pending_accounts.pop(region_key, None)
