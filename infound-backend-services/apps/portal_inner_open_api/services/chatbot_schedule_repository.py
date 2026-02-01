from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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


class ChatbotScheduleRepository:
    """
    通过 Samples 表字段管理 chatbot 发送状态（不再使用 schedule 表）。
    """

    SCENARIO_SHIPPED = "shipped"
    SCENARIO_CONTENT_PENDING = "content_pending"
    SCENARIO_NO_CONTENT_POSTED = "no_content_posted"

    STATUS_SHIPPED = "shipped"
    STATUS_CONTENT_PENDING = "content pending"
    STATUS_COMPLETED = "completed"

    NO_CONTENT_INTERVAL_DAYS = 5
    REPEAT_TIMES = 3  # repeat 3 times after the first send

    async def apply_sample_snapshot(
        self,
        session: AsyncSession,
        *,
        previous: Optional[SampleSnapshot],
        current: SampleSnapshot,
    ) -> None:
        curr_status = _normalize_status(current.status)
        now = _utcnow()

        # 首次插入避免触发一次性消息（与旧逻辑保持一致）。
        if previous is None:
            if curr_status == self.STATUS_SHIPPED:
                await self._mark_one_shot_sent(
                    session,
                    sample_id=current.sample_id,
                    column="chatbot_shipped_sent_at",
                    now=now,
                )
            elif curr_status == self.STATUS_CONTENT_PENDING:
                await self._mark_one_shot_sent(
                    session,
                    sample_id=current.sample_id,
                    column="chatbot_content_pending_sent_at",
                    now=now,
                )

        # 状态变化时无需写入字段；publisher 会在 sent_at 为空时发送一次性消息。

        # 重复提醒：已完成且内容为空 → 激活；否则关闭。
        if curr_status == self.STATUS_COMPLETED and _is_empty_content_summary(
            current.content_summary
        ):
            await self._activate_no_content_schedule(
                session,
                sample_id=current.sample_id,
                max_runs=self.REPEAT_TIMES + 1,
                now=now,
            )
        else:
            await self._deactivate_no_content(session, sample_id=current.sample_id)

    async def _mark_one_shot_sent(
        self,
        session: AsyncSession,
        *,
        sample_id: str,
        column: str,
        now: datetime,
    ) -> None:
        await session.execute(
            text(
                f"""
                UPDATE `samples`
                SET {column} = :now
                WHERE id = :sample_id AND {column} IS NULL;
                """
            ),
            {"sample_id": sample_id, "now": now},
        )

    async def _activate_no_content_schedule(
        self,
        session: AsyncSession,
        *,
        sample_id: str,
        max_runs: int,
        now: datetime,
    ) -> None:
        await session.execute(
            text(
                """
                UPDATE `samples`
                SET no_content_active = 1,
                    no_content_next_run_at = :now,
                    no_content_run_count = COALESCE(no_content_run_count, 0)
                WHERE id = :sample_id
                  AND (no_content_active IS NULL OR no_content_active = 0)
                  AND COALESCE(no_content_run_count, 0) < :max_runs;
                """
            ),
            {"sample_id": sample_id, "now": now, "max_runs": max_runs},
        )

    async def _deactivate_no_content(
        self,
        session: AsyncSession,
        *,
        sample_id: str,
    ) -> None:
        await session.execute(
            text(
                """
                UPDATE `samples`
                SET no_content_active = 0,
                    no_content_next_run_at = NULL
                WHERE id = :sample_id AND no_content_active = 1;
                """
            ),
            {"sample_id": sample_id},
        )


chatbot_schedule_repository = ChatbotScheduleRepository()
