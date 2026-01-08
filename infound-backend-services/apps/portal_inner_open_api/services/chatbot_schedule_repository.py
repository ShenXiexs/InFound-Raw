from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.logger import get_logger
from common.models.infound import Samples, SampleCrawlLogs

logger = get_logger()


@dataclass(frozen=True)
class SampleSnapshot:
    sample_id: str
    region: Optional[str]
    status: Optional[str]
    content_summary: Any
    ad_code: Any
    platform_product_id: Optional[str] = None
    platform_creator_username: Optional[str] = None
    platform_creator_id: Optional[str] = None
    platform_creator_display_name: Optional[str] = None


def _utcnow() -> datetime:
    return datetime.utcnow()


def _normalize_status(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return str(value).strip().lower() or None


def _is_empty_content_summary(summary: Any) -> bool:
    if not summary:
        return True
    if isinstance(summary, dict):
        summary = [summary]
    if isinstance(summary, list):
        for item in summary:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            # `logistics_snapshot` 只代表物流信息，不代表已发布内容；有 video/live 才算已发布。
            if item_type and item_type != "logistics":
                return False
            if any(
                str(item.get(key) or "").strip()
                for key in {"promotion_name", "promotion_time"}
            ) and item_type != "logistics":
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


class ChatbotScheduleRepository:


    TABLE_NAME = "sample_chatbot_schedules"

    SCENARIO_SHIPPED = "shipped"
    SCENARIO_CONTENT_PENDING = "content_pending"
    SCENARIO_NO_CONTENT_POSTED = "no_content_posted"
    SCENARIO_MISSING_AD_CODE = "missing_ad_code"

    STATUS_SHIPPED = "shipped"
    STATUS_CONTENT_PENDING = "content pending"
    STATUS_COMPLETED = "completed"

    NO_CONTENT_INTERVAL_DAYS = 5
    MISSING_AD_CODE_INTERVAL_DAYS = 3
    REPEAT_TIMES = 3  # repeat 3 times after the first send

    def __init__(self) -> None:
        self._ensured = False
        self._ensure_lock = asyncio.Lock()

    async def ensure_table(self, session: AsyncSession) -> None:
        if self._ensured:
            return
        async with self._ensure_lock:
            if self._ensured:
                return
            await session.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS `{self.TABLE_NAME}` (
                      `id` CHAR(36) NOT NULL,
                      `sample_id` CHAR(36) NOT NULL,
                      `scenario` VARCHAR(64) NOT NULL,
                      `region` VARCHAR(32) NULL,
                      `interval_days` INT NULL,
                      `max_runs` INT NOT NULL DEFAULT 1,
                      `run_count` INT NOT NULL DEFAULT 0,
                      `next_run_time` DATETIME(3) NOT NULL,
                      `last_run_time` DATETIME(3) NULL,
                      `active` TINYINT(1) NOT NULL DEFAULT 1,
                      `created_at` DATETIME(3) NOT NULL,
                      `updated_at` DATETIME(3) NOT NULL,
                      PRIMARY KEY (`id`),
                      UNIQUE KEY `uq_sample_scenario` (`sample_id`, `scenario`),
                      KEY `ix_next_run_time` (`next_run_time`),
                      KEY `ix_active` (`active`)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                    """
                )
            )
            self._ensured = True

    async def apply_sample_snapshot(
        self,
        session: AsyncSession,
        *,
        previous: Optional[SampleSnapshot],
        current: SampleSnapshot,
    ) -> None:
        await self.ensure_table(session)

        prev_status = _normalize_status(previous.status) if previous else None
        curr_status = _normalize_status(current.status)

        # One-shot status events.
        # Only trigger when we have a previous snapshot (avoid firing on first insert).
        if previous is not None and curr_status and curr_status != prev_status:
            if curr_status == self.STATUS_SHIPPED:
                await self._schedule_once(
                    session,
                    sample_id=current.sample_id,
                    scenario=self.SCENARIO_SHIPPED,
                    region=current.region,
                )
            elif curr_status == self.STATUS_CONTENT_PENDING:
                await self._schedule_once(
                    session,
                    sample_id=current.sample_id,
                    scenario=self.SCENARIO_CONTENT_PENDING,
                    region=current.region,
                )

        # Repeating reminders (create or cancel depending on current snapshot).
        if curr_status == self.STATUS_COMPLETED and _is_empty_content_summary(current.content_summary):
            await self._schedule_repeating(
                session,
                sample_id=current.sample_id,
                scenario=self.SCENARIO_NO_CONTENT_POSTED,
                region=current.region,
                interval_days=self.NO_CONTENT_INTERVAL_DAYS,
                max_runs=self.REPEAT_TIMES + 1,
            )
        else:
            await self._deactivate(
                session, sample_id=current.sample_id, scenario=self.SCENARIO_NO_CONTENT_POSTED
            )

        # 检查 missing_ad_code 场景的新条件
        # 条件1和2: 先验证 SampleCrawlLogs 表中存在对应记录
        has_crawl_log = await self._check_crawl_log_exists(
            session,
            platform_product_id=current.platform_product_id,
            platform_creator_display_name=current.platform_creator_display_name,
        )
        if not has_crawl_log:
            should_schedule = False
        else:
            # 条件3: Samples.content_summary 里有 type 为 video 的数据
            # 条件4: Samples.ad_code 为 null
            has_video = _has_video_in_content_summary(current.content_summary)
            ad_code_empty = _is_ad_code_empty(current.ad_code)
            should_schedule = has_video and ad_code_empty
        if should_schedule:
            await self._schedule_repeating(
                session,
                sample_id=current.sample_id,
                scenario=self.SCENARIO_MISSING_AD_CODE,
                region=current.region,
                interval_days=self.MISSING_AD_CODE_INTERVAL_DAYS,
                max_runs=self.REPEAT_TIMES + 1,
            )
        else:
            await self._deactivate(
                session, sample_id=current.sample_id, scenario=self.SCENARIO_MISSING_AD_CODE
            )

    async def _schedule_once(
        self,
        session: AsyncSession,
        *,
        sample_id: str,
        scenario: str,
        region: Optional[str],
    ) -> None:
        await self._upsert_schedule(
            session,
            sample_id=sample_id,
            scenario=scenario,
            region=region,
            interval_days=None,
            max_runs=1,
        )

    async def _schedule_repeating(
        self,
        session: AsyncSession,
        *,
        sample_id: str,
        scenario: str,
        region: Optional[str],
        interval_days: int,
        max_runs: int,
    ) -> None:
        await self._upsert_schedule(
            session,
            sample_id=sample_id,
            scenario=scenario,
            region=region,
            interval_days=interval_days,
            max_runs=max_runs,
        )

    async def _upsert_schedule(
        self,
        session: AsyncSession,
        *,
        sample_id: str,
        scenario: str,
        region: Optional[str],
        interval_days: Optional[int],
        max_runs: int,
    ) -> None:
        now = _utcnow()
        schedule_id = str(uuid4()).upper()
        await session.execute(
            text(
                f"""
                INSERT INTO `{self.TABLE_NAME}` (
                  id, sample_id, scenario, region, interval_days, max_runs, run_count,
                  next_run_time, last_run_time, active, created_at, updated_at
                ) VALUES (
                  :id, :sample_id, :scenario, :region, :interval_days, :max_runs, 0,
                  :next_run_time, NULL, 1, :now, :now
                )
                ON DUPLICATE KEY UPDATE
                  active = IF(active = 0 AND run_count < max_runs, 1, active),
                  next_run_time = IF(active = 0 AND run_count < max_runs, VALUES(next_run_time), next_run_time),
                  interval_days = IFNULL(interval_days, VALUES(interval_days)),
                  max_runs = GREATEST(max_runs, VALUES(max_runs)),
                  updated_at = VALUES(updated_at);
                """
            ),
            {
                "id": schedule_id,
                "sample_id": sample_id,
                "scenario": scenario,
                "region": region,
                "interval_days": interval_days,
                "max_runs": max_runs,
                "next_run_time": now,
                "now": now,
            },
        )

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

    async def _deactivate(self, session: AsyncSession, *, sample_id: str, scenario: str) -> None:
        now = _utcnow()
        await session.execute(
            text(
                f"""
                UPDATE `{self.TABLE_NAME}`
                SET active = 0, updated_at = :now
                WHERE sample_id = :sample_id AND scenario = :scenario AND active = 1;
                """
            ),
            {"sample_id": sample_id, "scenario": scenario, "now": now},
        )


chatbot_schedule_repository = ChatbotScheduleRepository()
