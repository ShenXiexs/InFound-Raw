from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

from aio_pika import DeliveryMode, Message
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.config import get_settings
from common.core.database import get_db
from common.core.logger import get_logger
from common.models.all import Samples, SampleCrawlLogs
from common.mq.connection import RabbitMQConnection

logger = get_logger()


@dataclass(frozen=True)
class ScheduleRow:
    id: str
    sample_id: str
    scenario: str
    region: Optional[str]
    interval_days: Optional[int]
    max_runs: int
    run_count: int


def _utcnow() -> datetime:
    return datetime.utcnow()


def _normalize_status(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return str(value).strip().lower() or None


def _is_empty_content_summary(summary: Any) -> bool:
    if not summary:
        return True
    if isinstance(summary, list):
        for item in summary:
            if not isinstance(item, dict):
                continue
            for key, value in item.items():
                if key in {
                    "promotion_like_count",
                    "promotion_view_count",
                    "promotion_order_count",
                    "promotion_comment_count",
                    "promotion_order_total_amount",
                    "promotion_name",
                    "promotion_time",
                } and value:
                    return False
                if key == "logistics_snapshot" and value:
                    return False
        return True
    return False


def _is_ad_code_empty(ad_code: Any) -> bool:
    if not ad_code:
        return True
    if isinstance(ad_code, list):
        return len(ad_code) == 0
    if isinstance(ad_code, dict):
        return len(ad_code) == 0
    return False


def _has_video_in_content_summary(content_summary: Any) -> bool:
    """检查 content_summary 中是否有 type 为 video 的数据"""
    if not content_summary:
        return False
    if isinstance(content_summary, dict):
        content_summary = [content_summary]
    if isinstance(content_summary, list):
        for item in content_summary:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "video":
                return True
    return False


class SampleChatbotService:
    """
    Chatbot producer: polls `sample_chatbot_schedules` written by inner API, and enqueues
    chat tasks to RabbitMQ for the dispatcher to send.

    This service does NOT detect sample status changes anymore.
    """

    TABLE_NAME = "sample_chatbot_schedules"

    SCENARIO_SHIPPED = "shipped"
    SCENARIO_CONTENT_PENDING = "content_pending"
    SCENARIO_NO_CONTENT_POSTED = "no_content_posted"
    SCENARIO_MISSING_AD_CODE = "missing_ad_code"

    STATUS_SHIPPED = "shipped"
    STATUS_CONTENT_PENDING = "content pending"
    STATUS_COMPLETED = "completed"

    SUPPORTED_REGION = "MX"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = get_logger().bind(service="sample_chatbot_schedule_runner")
        self.poll_interval = int(getattr(self.settings, "CHATBOT_POLL_INTERVAL_SECONDS", 15) or 15)
        self.batch_size = int(getattr(self.settings, "CHATBOT_BATCH_SIZE", 20) or 20)
        self.default_region = str(
            getattr(
                self.settings,
                "CHATBOT_DEFAULT_REGION",
                getattr(self.settings, "SAMPLE_DEFAULT_REGION", "MX"),
            )
            or "MX"
        ).upper()
        self.account_name = getattr(self.settings, "CHATBOT_ACCOUNT_NAME", None)
        self.operator_id = (
            getattr(self.settings, "CHATBOT_OPERATOR_ID", None)
            or getattr(self.settings, "SAMPLE_DEFAULT_OPERATOR_ID", None)
        )
        self._stop_event = asyncio.Event()
        self.accounts_catalog = self._load_sender_accounts()

        amqp_url = (
            f"amqp://{quote_plus(self.settings.RABBITMQ_USERNAME)}:"
            f"{quote_plus(self.settings.RABBITMQ_PASSWORD)}@"
            f"{self.settings.RABBITMQ_HOST}:{self.settings.RABBITMQ_PORT}/"
            f"{quote_plus(self.settings.RABBITMQ_VHOST)}"
        )
        self.publisher_conn = RabbitMQConnection(
            url=amqp_url,
            exchange_name=self.settings.RABBITMQ_EXCHANGE_NAME,
            routing_key=self.settings.RABBITMQ_ROUTING_KEY,
            queue_name=self.settings.RABBITMQ_QUEUE_NAME,
            prefetch_count=getattr(self.settings, "RABBITMQ_PREFETCH_COUNT", 1) or 1,
            reconnect_delay=getattr(self.settings, "RABBITMQ_RECONNECT_DELAY", 5),
            max_reconnect_attempts=getattr(self.settings, "RABBITMQ_MAX_RECONNECT_ATTEMPTS", 5),
            at_most_once=getattr(self.settings, "RABBITMQ_AT_MOST_ONCE", False),
        )

    async def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = await self._process_due_once()
                if not processed:
                    await self._sleep_interval()
            except Exception:
                self.logger.error("Unexpected error in chatbot schedule runner", exc_info=True)
                await self._sleep_interval()

    async def stop(self) -> None:
        self._stop_event.set()
        try:
            await self.publisher_conn.close()
        except Exception:
            pass

    async def _sleep_interval(self) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
        except asyncio.TimeoutError:
            pass

    async def _process_due_once(self) -> bool:
        async with get_db() as session:
            async with session.begin():
                due = await self._fetch_due_schedules(session, lock_rows=True)
                if not due:
                    return False
                for row in due:
                    try:
                        await self._handle_schedule(session, row)
                    except Exception:
                        self.logger.error(
                            "Failed to handle schedule row",
                            schedule_id=row.id,
                            sample_id=row.sample_id,
                            scenario=row.scenario,
                            exc_info=True,
                        )
            return True

    async def _fetch_due_schedules(
        self, session: AsyncSession, *, lock_rows: bool = False
    ) -> List[ScheduleRow]:
        now = _utcnow()
        suffix = " FOR UPDATE SKIP LOCKED" if lock_rows else ""
        try:
            result = await session.execute(
                text(
                    f"""
                    SELECT id, sample_id, scenario, region, interval_days, max_runs, run_count
                    FROM `{self.TABLE_NAME}`
                    WHERE active = 1
                      AND next_run_time <= :now
                      AND run_count < max_runs
                    ORDER BY next_run_time ASC
                    LIMIT :limit{suffix};
                    """
                ),
                {"now": now, "limit": self.batch_size},
            )
        except Exception:
            self.logger.warning(
                "Failed to query chatbot schedules (table missing or DB error)",
                table=self.TABLE_NAME,
                exc_info=True,
            )
            return []
        rows: List[ScheduleRow] = []
        for item in result.mappings().all():
            rows.append(
                ScheduleRow(
                    id=str(item["id"]),
                    sample_id=str(item["sample_id"]),
                    scenario=str(item["scenario"]),
                    region=item.get("region"),
                    interval_days=item.get("interval_days"),
                    max_runs=int(item.get("max_runs") or 1),
                    run_count=int(item.get("run_count") or 0),
                )
            )
        return rows

    async def _handle_schedule(self, session: AsyncSession, row: ScheduleRow) -> None:
        sample = await self._load_sample(session, row.sample_id)
        if not sample:
            await self._deactivate(session, row.id)
            return

        region = self._normalize_region(row.region or getattr(sample, "region", None) or self.default_region)
        if not self._is_region_supported(region):
            await self._deactivate(session, row.id)
            return

        if not await self._is_schedule_valid(session, row.scenario, sample):
            await self._deactivate(session, row.id)
            return

        sender = self._resolve_sender_account(region)
        payload = {
            "taskId": self._generate_uuid(),
            "scenario": row.scenario,
            "region": region,
            "sampleId": row.sample_id,
            "from": (sender.get("creator_id") if sender else None) or (self.operator_id or ""),
            "accountName": (sender.get("name") if sender else None) or self.account_name,
            "operatorId": (sender.get("creator_id") if sender else None) or (self.operator_id or ""),
        }
        await self._publish(payload)
        await self._mark_executed(session, row)

    async def _load_sample(self, session: AsyncSession, sample_id: str) -> Optional[Samples]:
        result = await session.execute(select(Samples).where(Samples.id == sample_id).limit(1))
        return result.scalars().first()

    async def _is_schedule_valid(self, session: AsyncSession, scenario: str, sample: Samples) -> bool:
        status = _normalize_status(getattr(sample, "status", None))
        if scenario == self.SCENARIO_SHIPPED:
            return status == self.STATUS_SHIPPED
        if scenario == self.SCENARIO_CONTENT_PENDING:
            return status == self.STATUS_CONTENT_PENDING
        if scenario == self.SCENARIO_NO_CONTENT_POSTED:
            return status == self.STATUS_COMPLETED and _is_empty_content_summary(getattr(sample, "content_summary", None))
        if scenario == self.SCENARIO_MISSING_AD_CODE:
            # 检查条件：检查新入库的 sample 数据
            # 条件1和2: 先验证 SampleCrawlLogs 表中存在对应记录
            has_crawl_log = await self._check_crawl_log_exists(
                session,
                platform_product_id=getattr(sample, "platform_product_id", None),
                platform_creator_display_name=getattr(sample, "platform_creator_display_name", None),
            )
            if not has_crawl_log:
                return False
            
            # 条件3: Samples.content_summary 里有 type 为 video 的数据
            # 条件4: Samples.ad_code 为 null
            content_summary = getattr(sample, "content_summary", None)
            ad_code = getattr(sample, "ad_code", None)
            has_video = _has_video_in_content_summary(content_summary)
            ad_code_empty = _is_ad_code_empty(ad_code)
            return has_video and ad_code_empty
        return False

    async def _check_crawl_log_exists(
        self,
        session: AsyncSession,
        *,
        platform_product_id: Optional[str],
        platform_creator_display_name: Optional[str],
    ) -> bool:
        """
        验证 SampleCrawlLogs 表中是否存在对应记录（通过 platform_product_id 和 platform_creator_display_name）。
        需要满足两个条件：
        1. SampleCrawlLogs.platform_product_id == Samples.platform_product_id
        2. SampleCrawlLogs.platform_creator_display_name == Samples.platform_creator_display_name
        """
        if not platform_product_id or not platform_creator_display_name:
            return False

        # 查询最新的记录
        stmt = select(
            SampleCrawlLogs.id,
        ).where(
            SampleCrawlLogs.platform_product_id == platform_product_id,
            SampleCrawlLogs.platform_creator_display_name == platform_creator_display_name,
        ).order_by(
            SampleCrawlLogs.crawl_date.desc(),
            SampleCrawlLogs.creation_time.desc(),
        ).limit(1)

        result = await session.execute(stmt)
        row = result.first()

        return row is not None

    async def _publish(self, payload: Dict[str, Any]) -> None:
        await self.publisher_conn.connect()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        message = Message(
            body=body,
            message_id=str(payload.get("taskId") or ""),
            delivery_mode=DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        await self.publisher_conn.exchange.publish(
            message, routing_key=self.publisher_conn.routing_key
        )
        self.logger.info(
            "Enqueued chat task",
            scenario=payload.get("scenario"),
            sample_id=payload.get("sampleId"),
        )

    async def _mark_executed(self, session: AsyncSession, row: ScheduleRow) -> None:
        now = _utcnow()
        new_count = row.run_count + 1
        active = 1
        next_time = now
        if new_count >= row.max_runs:
            active = 0
        else:
            if row.interval_days:
                next_time = now + timedelta(days=int(row.interval_days))
        await session.execute(
            text(
                f"""
                UPDATE `{self.TABLE_NAME}`
                SET run_count = :new_count,
                    last_run_time = :now,
                    next_run_time = :next_time,
                    active = :active,
                    updated_at = :now
                WHERE id = :id;
                """
            ),
            {
                "id": row.id,
                "new_count": new_count,
                "now": now,
                "next_time": next_time,
                "active": active,
            },
        )

    async def _deactivate(self, session: AsyncSession, schedule_id: str) -> None:
        now = _utcnow()
        await session.execute(
            text(
                f"""
                UPDATE `{self.TABLE_NAME}`
                SET active = 0, updated_at = :now
                WHERE id = :id;
                """
            ),
            {"id": schedule_id, "now": now},
        )

    @staticmethod
    def _generate_uuid() -> str:
        return str(uuid.uuid4()).upper()

    def _normalize_region(self, region: Optional[str]) -> str:
        return str(region or "").strip().upper()

    def _is_region_supported(self, region: str) -> bool:
        return region == self.SUPPORTED_REGION

    def _load_sender_accounts(self) -> List[Dict[str, Any]]:
        path = Path(getattr(self.settings, "SAMPLE_ACCOUNT_CONFIG_PATH", "configs/accounts.json"))
        if not path.exists():
            self.logger.warning("Account config file missing", path=str(path))
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            accounts = data.get("accounts", [])
            if isinstance(accounts, list):
                return accounts
        except Exception:
            self.logger.warning("Failed to load account config", path=str(path), exc_info=True)
        return []

    def _resolve_sender_account(self, region: str) -> Optional[Dict[str, Any]]:
        region_upper = region.upper()
        desired = (self.account_name or "").strip()
        if desired:
            for account in self.accounts_catalog:
                if not account.get("enabled", True):
                    continue
                if str(account.get("name") or "").strip() == desired:
                    return account
        for account in self.accounts_catalog:
            if not account.get("enabled", True):
                continue
            acc_region = str(account.get("region") or "").strip().upper()
            if acc_region and acc_region != region_upper:
                continue
            return account
        return None
