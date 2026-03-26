from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.models.entities import CurrentUserInfo
from apps.portal_seller_open_api.models.task_runtime import (
    SellerRpaTaskClaimResult,
    SellerRpaTaskHeartbeatResult,
    SellerRpaTaskReportRequest,
    SellerRpaTaskReportResult,
    SellerRpaTaskStatus,
    SellerRpaTaskType,
)
from apps.portal_seller_open_api.services.normalization import clean_text
from shared_domain.models.infound import SellerTkRpaTaskPlans


class SellerRpaTaskRuntimeService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def claim(
        self,
        current_user: CurrentUserInfo,
        task_type: SellerRpaTaskType,
        task_id: str | None = None,
    ) -> SellerRpaTaskClaimResult | None:
        utc_now = datetime.utcnow()
        stmt = select(SellerTkRpaTaskPlans).where(
            SellerTkRpaTaskPlans.user_id == current_user.user_id,
            SellerTkRpaTaskPlans.task_type == task_type.value,
            SellerTkRpaTaskPlans.status == SellerRpaTaskStatus.PENDING.value,
            SellerTkRpaTaskPlans.scheduled_time <= utc_now,
        )
        normalized_task_id = clean_text(task_id)
        if normalized_task_id:
            stmt = stmt.where(SellerTkRpaTaskPlans.id == normalized_task_id)
        else:
            stmt = stmt.order_by(
                SellerTkRpaTaskPlans.scheduled_time.asc(),
                SellerTkRpaTaskPlans.creation_time.asc(),
                SellerTkRpaTaskPlans.id.asc(),
            )

        stmt = stmt.limit(1).with_for_update(skip_locked=True)
        task_plan = await self._scalar_one_or_none(stmt)
        if task_plan is None:
            await self.db_session.rollback()
            return None

        task_plan.status = SellerRpaTaskStatus.RUNNING.value
        if task_plan.start_time is None:
            task_plan.start_time = utc_now
        task_plan.heartbeat_at = utc_now
        task_plan.last_modifier_id = current_user.user_id
        task_plan.last_modification_time = utc_now
        await self.db_session.commit()

        return SellerRpaTaskClaimResult(
            id=task_plan.id,
            task_type=str(task_plan.task_type),
            task_status=str(task_plan.status),
            task_data=task_plan.task_payload,
            created_at=task_plan.creation_time,
            updated_at=task_plan.last_modification_time,
            scheduled_time=task_plan.scheduled_time,
            start_time=task_plan.start_time,
            end_time=task_plan.end_time,
            heartbeat_at=task_plan.heartbeat_at,
        )

    async def heartbeat(
        self,
        current_user: CurrentUserInfo,
        task_id: str,
    ) -> SellerRpaTaskHeartbeatResult:
        task_plan = await self._get_task_plan(current_user.user_id, task_id)
        if task_plan is None:
            raise ValueError("task_id not found")
        if task_plan.status != SellerRpaTaskStatus.RUNNING.value:
            raise ValueError("task is not running")

        utc_now = datetime.utcnow()
        task_plan.heartbeat_at = utc_now
        task_plan.last_modifier_id = current_user.user_id
        task_plan.last_modification_time = utc_now
        await self.db_session.commit()

        return SellerRpaTaskHeartbeatResult(
            task_id=task_plan.id,
            task_status=str(task_plan.status),
            heartbeat_at=utc_now,
        )

    async def report(
        self,
        current_user: CurrentUserInfo,
        task_id: str,
        payload: SellerRpaTaskReportRequest,
    ) -> SellerRpaTaskReportResult:
        task_plan = await self._get_task_plan(current_user.user_id, task_id)
        if task_plan is None:
            raise ValueError("task_id not found")

        utc_now = datetime.utcnow()
        normalized_error = clean_text(payload.error)
        task_plan.status = payload.task_status.value
        task_plan.end_time = utc_now
        task_plan.last_modifier_id = current_user.user_id
        task_plan.last_modification_time = utc_now

        if payload.task_status == SellerRpaTaskStatus.FAILED:
            task_plan.error_msg = normalized_error
        elif payload.task_status in {
            SellerRpaTaskStatus.COMPLETED,
            SellerRpaTaskStatus.CANCELLED,
        }:
            task_plan.error_msg = None

        await self.db_session.commit()

        return SellerRpaTaskReportResult(
            task_id=task_plan.id,
            task_status=str(task_plan.status),
            end_time=utc_now,
            error=normalized_error,
        )

    async def _get_task_plan(
        self,
        user_id: str,
        task_id: str,
    ) -> SellerTkRpaTaskPlans | None:
        stmt = (
            select(SellerTkRpaTaskPlans)
            .where(
                SellerTkRpaTaskPlans.user_id == user_id,
                SellerTkRpaTaskPlans.id == str(task_id).strip(),
            )
            .limit(1)
        )
        return await self._scalar_one_or_none(stmt)

    async def _scalar_one_or_none(
        self, stmt: Select[tuple[SellerTkRpaTaskPlans]]
    ) -> SellerTkRpaTaskPlans | None:
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()
