import asyncio
import json
from pathlib import Path
from typing import Optional, List
from urllib.parse import quote_plus

import aio_pika
from aio_pika import ExchangeType

from common.core.config import get_settings
from common.core.exceptions import MessageProcessingError
from common.core.logger import get_logger
from common.mq.connection import RabbitMQConnection
from common.mq.consumer_base import ConsumerBase

from .services.outreach_dispatcher_service import OutreachChatbotTask
from .services.outreach_worker_pool import OutreachChatbotWorkerPool


class CrawlerConsumer(ConsumerBase):
    """Outreach chatbot dispatcher consumer (sender + decision + contact info)."""

    def __init__(self, *, rabbitmq_config: Optional[dict] = None) -> None:
        self.settings = get_settings()
        rabbitmq_config = rabbitmq_config or {}
        amqp_url = (
            f"amqp://{quote_plus(self.settings.RABBITMQ_USERNAME)}:"
            f"{quote_plus(self.settings.RABBITMQ_PASSWORD)}@"
            f"{self.settings.RABBITMQ_HOST}:{self.settings.RABBITMQ_PORT}/"
            f"{quote_plus(self.settings.RABBITMQ_VHOST)}"
        )
        exchange_type = ExchangeType.TOPIC
        rabbitmq_conn = RabbitMQConnection(
            url=amqp_url,
            exchange_name=rabbitmq_config.get(
                "exchange_name", self.settings.RABBITMQ_EXCHANGE_NAME
            ),
            routing_key=rabbitmq_config.get(
                "routing_key", self.settings.RABBITMQ_ROUTING_KEY
            ),
            queue_name=rabbitmq_config.get(
                "queue_name", self.settings.RABBITMQ_QUEUE_NAME
            ),
            at_most_once=rabbitmq_config.get(
                "at_most_once", getattr(self.settings, "RABBITMQ_AT_MOST_ONCE", False)
            ),
            prefetch_count=rabbitmq_config.get(
                "prefetch_count", self.settings.RABBITMQ_PREFETCH_COUNT
            ),
            reconnect_delay=rabbitmq_config.get(
                "reconnect_delay", self.settings.RABBITMQ_RECONNECT_DELAY
            ),
            max_reconnect_attempts=rabbitmq_config.get(
                "max_reconnect_attempts", self.settings.RABBITMQ_MAX_RECONNECT_ATTEMPTS
            ),
            exchange_type=exchange_type,
            queue_arguments=rabbitmq_config.get("queue_arguments"),
            queue_durable=rabbitmq_config.get("queue_durable", True),
            queue_auto_delete=rabbitmq_config.get("queue_auto_delete", False),
            queue_exclusive=rabbitmq_config.get("queue_exclusive", False),
            dlq_arguments=rabbitmq_config.get("dlq_arguments"),
            dlq_durable=rabbitmq_config.get("dlq_durable", True),
            dlq_auto_delete=rabbitmq_config.get("dlq_auto_delete", False),
        )
        super().__init__(rabbitmq_conn)
        self.logger = get_logger().bind(consumer="outreach_chatbot")
        self._idle_event: Optional[asyncio.Event] = None
        self.pool = OutreachChatbotWorkerPool(
            worker_count=int(getattr(self.settings, "OUTREACH_CHATBOT_WORKER_COUNT", 2) or 2),
            account_names=self._load_account_names(),
        )

    async def start(self) -> None:
        if not getattr(self.settings, "CHATBOT_ENABLED", True):
            self.logger.warning("Outreach chatbot disabled via config; idling")
            self._idle_event = asyncio.Event()
            await self._idle_event.wait()
            return

        await self.pool.start()
        await super().start()

    async def stop(self) -> None:
        if not getattr(self.settings, "CHATBOT_ENABLED", True) and self._idle_event:
            self._idle_event.set()
            return
        await super().stop()
        await self.pool.close()

    async def drain_and_stop(
        self,
        *,
        idle_seconds: float = 3.0,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.logger.info(
            "Draining outreach chatbot consumer",
            queue=self.rabbitmq_conn.queue_name,
            idle_seconds=idle_seconds,
            timeout_seconds=timeout_seconds,
        )
        deadline = asyncio.get_running_loop().time() + max(timeout_seconds, 0)
        idle_since = None
        while asyncio.get_running_loop().time() < deadline:
            backlog = await self._get_queue_backlog()
            queued, inflight = self.pool.pending_counts()
            if (backlog in (None, 0)) and queued == 0 and inflight == 0:
                if idle_since is None:
                    idle_since = asyncio.get_running_loop().time()
                if asyncio.get_running_loop().time() - idle_since >= idle_seconds:
                    break
            else:
                idle_since = None
            await asyncio.sleep(0.5)
        await self.stop()

    async def _get_queue_backlog(self) -> int | None:
        queue = getattr(self.rabbitmq_conn, "queue", None)
        if not queue:
            return None
        try:
            result = await queue.declare(passive=True)
            return getattr(result, "message_count", None)
        except Exception:
            return None

    async def process_message_body(self, message_id: str, body: object) -> None:
        """
        处理 MQ 消息体：
        - 批量：{ "taskId": "...", "tasks": [ {...}, ... ] }
        - 单条：{ ... }
        - 纯数组：[ {...}, ... ]
        """
        if isinstance(body, list):
            items = body
            is_batch = True
            batch_task_id = str(message_id)
            base_payload = {}
        elif isinstance(body, dict):
            tasks = body.get("tasks")
            is_batch = isinstance(tasks, list)
            batch_task_id = str(body.get("taskId") or message_id)
            base_payload = {key: value for key, value in body.items() if key != "tasks"}
            items = tasks if is_batch else [body]
        else:
            self.logger.warning("Unsupported message body type", message_id=message_id)
            return
        if not items:
            self.logger.warning("Empty tasks array in message", batch_task_id=batch_task_id)
            return

        self.logger.info(
            "Processing outreach chat tasks",
            batch_task_id=batch_task_id,
            task_count=len(items),
            is_batch=is_batch,
        )

        futures = []
        payloads = []
        for idx, raw in enumerate(items, start=1):
            if not isinstance(raw, dict):
                await self._publish_to_dead_letter_strict(
                    json.dumps(raw, ensure_ascii=False).encode("utf-8"),
                    message_id=None,
                    reason=f"task payload is not an object (index={idx})",
                )
                continue

            payload = dict(base_payload)
            payload.update(raw)
            try:
                task = OutreachChatbotTask.from_payload(payload)
            except Exception as exc:
                await self._publish_to_dead_letter_strict(
                    json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    message_id=str(payload.get("taskId") or "") or None,
                    reason=f"invalid outreach task (index={idx}): {exc}",
                )
                continue

            fut = await self.pool.submit(task)
            futures.append(fut)
            payloads.append(payload)

        if not futures:
            return

        results = await asyncio.gather(*futures, return_exceptions=True)
        success_count = 0
        error_count = 0
        for payload, result in zip(payloads, results):
            if isinstance(result, Exception):
                error_count += 1
                await self._publish_to_dead_letter_strict(
                    json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    message_id=str(payload.get("taskId") or "") or None,
                    reason=f"dispatch failed: {result}",
                )
                self.logger.error(
                    "Outreach chat task dispatch failed",
                    task_id=payload.get("taskId"),
                    creator_id=payload.get("platformCreatorId") or payload.get("platform_creator_id"),
                    error=str(result),
                )
            else:
                success_count += 1
                self.logger.info(
                    "Outreach chat task dispatched",
                    task_id=payload.get("taskId"),
                    creator_id=payload.get("platformCreatorId") or payload.get("platform_creator_id"),
                )

        self.logger.info(
            "Outreach chat tasks processed",
            batch_task_id=batch_task_id,
            success_count=success_count,
            error_count=error_count,
            total_count=len(results),
            is_batch=is_batch,
        )

    async def _publish_to_dead_letter_strict(
        self,
        body: bytes,
        *,
        message_id: Optional[str],
        reason: str,
    ) -> None:
        dlx_exchange = getattr(self.rabbitmq_conn, "dlx_exchange", None)
        if not dlx_exchange:
            raise MessageProcessingError("Dead-letter exchange is not available")

        headers = {"x-error": reason}
        if message_id:
            headers["x-original-message-id"] = message_id

        try:
            await dlx_exchange.publish(
                aio_pika.Message(
                    body=body,
                    message_id=message_id,
                    headers=headers,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                ),
                routing_key=self.rabbitmq_conn.dl_routing_key,
            )
        except Exception:
            self.logger.warning("Failed to publish to dead-letter exchange", exc_info=True)

    def _load_account_names(self) -> List[Optional[str]]:
        desired = str(getattr(self.settings, "CHATBOT_ACCOUNT_NAME", "") or "").strip()
        if desired:
            return [desired]

        path = Path(getattr(self.settings, "SAMPLE_ACCOUNT_CONFIG_PATH", "configs/accounts.json"))
        if not path.exists():
            self.logger.warning("Account config file missing", path=str(path))
            return [None]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            accounts = data.get("accounts", [])
            if not isinstance(accounts, list):
                return [None]
            region = str(
                getattr(
                    self.settings,
                    "CHATBOT_DEFAULT_REGION",
                    getattr(self.settings, "SAMPLE_DEFAULT_REGION", "MX"),
                )
                or "MX"
            ).upper()
            names = []
            for account in accounts:
                if not account.get("enabled", True):
                    continue
                acc_region = str(account.get("region") or "").upper()
                if acc_region and acc_region != region:
                    continue
                name = str(account.get("name") or "").strip()
                if name:
                    names.append(name)
            if names:
                return names
            names = [
                str(account.get("name") or "").strip()
                for account in accounts
                if account.get("enabled", True)
            ]
            return [name for name in names if name] or [None]
        except Exception:
            self.logger.warning("Failed to load account config", path=str(path), exc_info=True)
            return [None]
