from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_inner_open_api.core.config import Settings
from apps.portal_inner_open_api.core.deps import (
    get_db_session,
    get_chatbot_message_builder,
)
from apps.portal_inner_open_api.services.chatbot_schedule_repository import (
    _is_empty_content_summary,
    _normalize_status,
    chatbot_schedule_repository,
)
from shared_domain.models.infound import Samples, Creators
from core_base import get_logger

logger = get_logger()


@dataclass(frozen=True)
class SampleScheduleRow:
    sample_id: str
    scenario: str
    region: Optional[str]
    no_content_run_count: int


def _utcnow() -> datetime:
    return datetime.utcnow()


class ChatbotSchedulePublisher:
    """
    轮询 Samples 表中的 chatbot 调度字段，发布到 RabbitMQ。

    这在 inner API 进程内以后台任务运行。
    """

    SCENARIO_SHIPPED = "shipped"
    SCENARIO_CONTENT_PENDING = "content_pending"
    SCENARIO_NO_CONTENT_POSTED = "no_content_posted"

    STATUS_SHIPPED = "shipped"
    STATUS_CONTENT_PENDING = "content pending"
    STATUS_COMPLETED = "completed"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = logger.bind(component="chatbot_schedule_publisher")
        self.poll_interval = int(
            getattr(self.settings, "CHATBOT_SCHEDULE_POLL_INTERVAL_SECONDS", 15) or 15
        )
        self.batch_size = int(
            getattr(self.settings, "CHATBOT_SCHEDULE_BATCH_SIZE", 20) or 20
        )
        self.supported_region = str(
            getattr(self.settings, "CHATBOT_SCHEDULE_SUPPORTED_REGION", "MX") or "MX"
        ).upper()
        self.no_content_interval_days = int(
            getattr(chatbot_schedule_repository, "NO_CONTENT_INTERVAL_DAYS", 5) or 5
        )
        self.no_content_max_runs = (
            int(getattr(chatbot_schedule_repository, "REPEAT_TIMES", 3) or 3) + 1
        )
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
                self.logger.error(
                    "Unexpected error in chatbot schedule publisher", exc_info=True
                )
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
            async with get_db_session() as session:
                due = await self._fetch_due_samples(session, lock_rows=True, limit=1)
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
                        sample_id=row.sample_id,
                        scenario=row.scenario,
                        exc_info=True,
                    )
                    continue
                if not task:
                    if row.scenario == self.SCENARIO_NO_CONTENT_POSTED:
                        await self._deactivate_no_content(session, row.sample_id)
                    continue
                await self._mark_executed(session, row)

            try:
                if task:
                    await RabbitMQProducer.publish_batch_chatbot_messages([task])
            except Exception:
                self.logger.error(
                    "Failed to publish schedule task after update",
                    sample_id=getattr(row, "sample_id", None),
                    scenario=getattr(row, "scenario", None),
                    exc_info=True,
                )
        return processed

    async def _fetch_due_samples(
        self,
        session: AsyncSession,
        *,
        lock_rows: bool = False,
        limit: Optional[int] = None,
    ) -> List[SampleScheduleRow]:
        now = _utcnow()
        limit_value = int(limit or self.batch_size)
        suffix = " FOR UPDATE SKIP LOCKED" if lock_rows else ""
        try:
            result = await session.execute(
                text(f"""
                    SELECT id, region,
                      CASE
                        WHEN LOWER(TRIM(status)) = :status_shipped
                             AND chatbot_shipped_sent_at IS NULL
                          THEN :scenario_shipped
                        WHEN LOWER(TRIM(status)) = :status_content_pending
                             AND chatbot_content_pending_sent_at IS NULL
                          THEN :scenario_content_pending
                        WHEN LOWER(TRIM(status)) = :status_completed
                             AND no_content_active = 1
                             AND no_content_next_run_at IS NOT NULL
                             AND no_content_next_run_at <= :now
                             AND COALESCE(no_content_run_count, 0) < :max_runs
                          THEN :scenario_no_content
                        ELSE NULL
                      END AS scenario,
                      COALESCE(no_content_run_count, 0) AS no_content_run_count
                    FROM `samples`
                    WHERE
                      (LOWER(TRIM(status)) = :status_shipped AND chatbot_shipped_sent_at IS NULL)
                      OR (LOWER(TRIM(status)) = :status_content_pending AND chatbot_content_pending_sent_at IS NULL)
                      OR (
                        LOWER(TRIM(status)) = :status_completed
                        AND no_content_active = 1
                        AND no_content_next_run_at IS NOT NULL
                        AND no_content_next_run_at <= :now
                        AND COALESCE(no_content_run_count, 0) < :max_runs
                      )
                    ORDER BY
                      CASE
                        WHEN LOWER(TRIM(status)) = :status_completed AND no_content_active = 1
                          THEN no_content_next_run_at
                        ELSE :now
                      END ASC
                    LIMIT :limit{suffix};
                    """),
                {
                    "status_shipped": self.STATUS_SHIPPED,
                    "status_content_pending": self.STATUS_CONTENT_PENDING,
                    "status_completed": self.STATUS_COMPLETED,
                    "scenario_shipped": self.SCENARIO_SHIPPED,
                    "scenario_content_pending": self.SCENARIO_CONTENT_PENDING,
                    "scenario_no_content": self.SCENARIO_NO_CONTENT_POSTED,
                    "now": now,
                    "max_runs": self.no_content_max_runs,
                    "limit": limit_value,
                },
            )
        except Exception:
            self.logger.error(
                "Failed to query chatbot schedules from samples",
                exc_info=True,
            )
            return []

        rows: List[SampleScheduleRow] = []
        for item in result.mappings().all():
            scenario = item.get("scenario")
            if not scenario:
                continue
            rows.append(
                SampleScheduleRow(
                    sample_id=str(item["id"]),
                    scenario=str(scenario),
                    region=item.get("region"),
                    no_content_run_count=int(item.get("no_content_run_count") or 0),
                )
            )
        return rows

    async def _build_task_for_schedule(
        self, session: AsyncSession, row: SampleScheduleRow
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
        chatbot_message_builder = get_chatbot_message_builder()
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

    async def _load_sample(
        self, session: AsyncSession, sample_id: str
    ) -> Optional[Samples]:
        result = await session.execute(
            select(Samples).where(Samples.id == sample_id).limit(1)
        )
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
        return False

    async def _mark_executed(
        self, session: AsyncSession, row: SampleScheduleRow
    ) -> None:
        now = _utcnow()
        if row.scenario == self.SCENARIO_SHIPPED:
            await session.execute(
                text("""
                    UPDATE `samples`
                    SET chatbot_shipped_sent_at = :now
                    WHERE id = :sample_id AND chatbot_shipped_sent_at IS NULL;
                    """),
                {"sample_id": row.sample_id, "now": now},
            )
            return
        if row.scenario == self.SCENARIO_CONTENT_PENDING:
            await session.execute(
                text("""
                    UPDATE `samples`
                    SET chatbot_content_pending_sent_at = :now
                    WHERE id = :sample_id AND chatbot_content_pending_sent_at IS NULL;
                    """),
                {"sample_id": row.sample_id, "now": now},
            )
            return
        if row.scenario != self.SCENARIO_NO_CONTENT_POSTED:
            return

        new_count = row.no_content_run_count + 1
        active = 1
        next_time = None
        if new_count >= self.no_content_max_runs:
            active = 0
        else:
            next_time = now + timedelta(days=self.no_content_interval_days)

        await session.execute(
            text("""
                UPDATE `samples`
                SET no_content_run_count = :new_count,
                    no_content_next_run_at = :next_time,
                    no_content_active = :active
                WHERE id = :sample_id;
                """),
            {
                "sample_id": row.sample_id,
                "new_count": new_count,
                "next_time": next_time,
                "active": active,
            },
        )

    async def _deactivate_no_content(
        self, session: AsyncSession, sample_id: str
    ) -> None:
        await session.execute(
            text("""
                UPDATE `samples`
                SET no_content_active = 0,
                    no_content_next_run_at = NULL
                WHERE id = :sample_id;
                """),
            {"sample_id": sample_id},
        )


chatbot_schedule_publisher = ChatbotSchedulePublisher()
