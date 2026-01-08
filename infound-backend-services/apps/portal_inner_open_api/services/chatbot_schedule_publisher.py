from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.config import get_settings
from common.core.database import DatabaseManager
from common.core.logger import get_logger
from common.models.infound import Samples, Creators
from common.services.rabbitmq_producer import RabbitMQProducer
from apps.portal_inner_open_api.services.chatbot_message_builder import (
    chatbot_message_builder,
)
from apps.portal_inner_open_api.services.chatbot_schedule_repository import (
    _is_ad_code_empty,
    _is_empty_content_summary,
    _normalize_status,
)


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


class ChatbotSchedulePublisher:
    """
    Polls `sample_chatbot_schedules` and publishes due tasks to RabbitMQ.

    This runs inside inner API process (background task) so that `sample_chatbot`
    can stay as a sender-only MQ consumer.
    """

    TABLE_NAME = "sample_chatbot_schedules"

    SCENARIO_SHIPPED = "shipped"
    SCENARIO_CONTENT_PENDING = "content_pending"
    SCENARIO_NO_CONTENT_POSTED = "no_content_posted"
    SCENARIO_MISSING_AD_CODE = "missing_ad_code"

    STATUS_SHIPPED = "shipped"
    STATUS_CONTENT_PENDING = "content pending"
    STATUS_COMPLETED = "completed"

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = logger.bind(component="chatbot_schedule_publisher")
        self.poll_interval = int(
            getattr(self.settings, "CHATBOT_SCHEDULE_POLL_INTERVAL_SECONDS", 15) or 15
        )
        self.batch_size = int(getattr(self.settings, "CHATBOT_SCHEDULE_BATCH_SIZE", 20) or 20)
        self.supported_region = str(
            getattr(self.settings, "CHATBOT_SCHEDULE_SUPPORTED_REGION", "MX") or "MX"
        ).upper()
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self.run())
        self.logger.info(
            "Chatbot schedule publisher started",
            poll_interval=self.poll_interval,
            batch_size=self.batch_size,
            supported_region=self.supported_region,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            finally:
                self._task = None
        self.logger.info("Chatbot schedule publisher stopped")

    async def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = await self._process_due_once()
                if not processed:
                    await self._sleep_interval()
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger.error("Unexpected error in chatbot schedule publisher", exc_info=True)
                await self._sleep_interval()

    async def _sleep_interval(self) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
        except asyncio.TimeoutError:
            return

    async def _process_due_once(self) -> bool:
        processed = False
        remaining = max(self.batch_size, 0)
        while remaining > 0:
            task = None
            row = None
            async with DatabaseManager.get_session() as session:
                due = await self._fetch_due_schedules(session, lock_rows=True, limit=1)
                if not due:
                    return processed

                row = due[0]
                processed = True
                remaining -= 1
                try:
                    task = await self._build_task_for_schedule(session, row)
                except Exception:
                    self.logger.error(
                        "Failed to build schedule task",
                        schedule_id=row.id,
                        sample_id=row.sample_id,
                        scenario=row.scenario,
                        exc_info=True,
                    )
                    continue
                if not task:
                    await self._deactivate(session, row.id)
                    continue
                await self._mark_executed(session, row)

            try:
                if task:
                    await RabbitMQProducer.publish_batch_chatbot_messages([task])
            except Exception:
                self.logger.error(
                    "Failed to publish schedule task after update",
                    schedule_id=getattr(row, "id", None),
                    sample_id=getattr(row, "sample_id", None),
                    scenario=getattr(row, "scenario", None),
                    exc_info=True,
                )
        return processed

    async def _fetch_due_schedules(
        self, session: AsyncSession, *, lock_rows: bool = False, limit: Optional[int] = None
    ) -> List[ScheduleRow]:
        now = _utcnow()
        limit_value = int(limit or self.batch_size)
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
                {"now": now, "limit": limit_value},
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

    async def _build_task_for_schedule(
        self, session: AsyncSession, row: ScheduleRow
    ) -> Optional[dict]:
        sample = await self._load_sample(session, row.sample_id)
        if not sample:
            return None

        region = str(row.region or getattr(sample, "region", None) or "MX").upper()
        if region != self.supported_region:
            return None

        if not self._is_schedule_valid(row.scenario, sample):
            return None

        creator_whatsapp = await self._load_creator_whatsapp(
            session, getattr(sample, "platform_creator_id", None)
        )
        messages = await chatbot_message_builder.build_messages(
            session=session,
            scenario=row.scenario,
            sample=sample,
            creator_whatsapp=creator_whatsapp,
        )
        if not messages:
            return None
        platform_creator_id = getattr(sample, "platform_creator_id", None)
        if not platform_creator_id:
            return None

        return {
            "region": region,
            "platformCreatorId": platform_creator_id,
            "messages": messages,
        }

    async def _load_sample(self, session: AsyncSession, sample_id: str) -> Optional[Samples]:
        result = await session.execute(select(Samples).where(Samples.id == sample_id).limit(1))
        return result.scalars().first()

    async def _load_creator_whatsapp(
        self, session: AsyncSession, platform_creator_id: Optional[str]
    ) -> Optional[str]:
        if not platform_creator_id:
            return None
        result = await session.execute(
            select(Creators.whatsapp)
            .where(Creators.platform_creator_id == platform_creator_id)
            .limit(1)
        )
        row = result.first()
        return row[0] if row else None

    def _is_schedule_valid(self, scenario: str, sample: Samples) -> bool:
        status = _normalize_status(getattr(sample, "status", None))
        if scenario == self.SCENARIO_SHIPPED:
            return status == self.STATUS_SHIPPED
        if scenario == self.SCENARIO_CONTENT_PENDING:
            return status == self.STATUS_CONTENT_PENDING
        if scenario == self.SCENARIO_NO_CONTENT_POSTED:
            return status == self.STATUS_COMPLETED and _is_empty_content_summary(
                getattr(sample, "content_summary", None)
            )
        if scenario == self.SCENARIO_MISSING_AD_CODE:
            return _is_ad_code_empty(getattr(sample, "ad_code", None))
        return False

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


chatbot_schedule_publisher = ChatbotSchedulePublisher()
