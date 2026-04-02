from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.core.config import Settings
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
from apps.portal_seller_open_api.services.task_slot_dispatch_service import (
    SellerRpaTaskSingleSlotDispatchService,
)
from core_base import get_logger
from shared_domain import DatabaseManager
from shared_domain.models.infound import SellerTkRpaTaskPlans


class SellerRpaTaskRuntimeService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.logger = get_logger(self.__class__.__name__)

    async def claim(
        self,
        current_user: CurrentUserInfo,
        task_type: SellerRpaTaskType,
        task_id: str | None = None,
    ) -> SellerRpaTaskClaimResult | None:
        async with DatabaseManager.get_session() as session:
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
            task_plan = await self._scalar_one_or_none(session, stmt)
            if task_plan is None:
                if normalized_task_id:
                    await self._log_claim_miss_diagnostics(
                        session,
                        user_id=current_user.user_id,
                        task_id=normalized_task_id,
                        task_type=task_type.value,
                    )
                await session.rollback()
                return None

            previous_status = str(task_plan.status or "").strip().upper()
            previous_start_time = task_plan.start_time
            previous_heartbeat_at = task_plan.heartbeat_at
            task_plan.status = SellerRpaTaskStatus.RUNNING.value
            if task_plan.start_time is None:
                task_plan.start_time = utc_now
            task_plan.heartbeat_at = utc_now
            task_plan.last_modifier_id = current_user.user_id
            task_plan.last_modification_time = utc_now
            await session.commit()

            if task_plan.start_time is None or task_plan.heartbeat_at is None:
                self.logger.error(
                    "RPA 任务 claim 后运行态不变量异常",
                    task_id=task_plan.id,
                    user_id=current_user.user_id,
                    task_type=task_plan.task_type,
                    previous_status=previous_status,
                    previous_start_time=previous_start_time,
                    previous_heartbeat_at=previous_heartbeat_at,
                    current_start_time=task_plan.start_time,
                    current_heartbeat_at=task_plan.heartbeat_at,
                )
            else:
                self.logger.info(
                    "RPA 任务已 claim 并切换为 RUNNING",
                    task_id=task_plan.id,
                    user_id=current_user.user_id,
                    task_type=task_plan.task_type,
                    previous_status=previous_status,
                    previous_start_time=previous_start_time,
                    previous_heartbeat_at=previous_heartbeat_at,
                    current_start_time=task_plan.start_time,
                    current_heartbeat_at=task_plan.heartbeat_at,
                )

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
        async with DatabaseManager.get_session() as session:
            task_plan = await self._get_task_plan(session, current_user.user_id, task_id)
            if task_plan is None:
                raise ValueError("task_id not found")
            if task_plan.status != SellerRpaTaskStatus.RUNNING.value:
                raise ValueError("task is not running")

            utc_now = datetime.utcnow()
            task_plan.heartbeat_at = utc_now
            task_plan.last_modifier_id = current_user.user_id
            task_plan.last_modification_time = utc_now
            await session.commit()

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
        async with DatabaseManager.get_session() as session:
            task_plan = await self._get_task_plan(session, current_user.user_id, task_id)
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

            await self._sync_contract_monitor_log_status(
                session,
                task_plan=task_plan,
                current_user=current_user,
                utc_now=utc_now,
                task_status=payload.task_status,
                normalized_error=normalized_error,
            )

            await session.commit()

            slot_dispatch_service = SellerRpaTaskSingleSlotDispatchService(
                session, self.settings
            )
            await slot_dispatch_service.dispatch_next_pending_task(
                user_id=current_user.user_id,
                task_type=str(task_plan.task_type or ""),
            )

            return SellerRpaTaskReportResult(
                task_id=task_plan.id,
                task_status=str(task_plan.status),
                end_time=utc_now,
                error=normalized_error,
            )

    async def _get_task_plan(
        self,
        session: AsyncSession,
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
        return await self._scalar_one_or_none(session, stmt)

    async def _log_claim_miss_diagnostics(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        task_id: str,
        task_type: str,
    ) -> None:
        stmt = (
            select(SellerTkRpaTaskPlans)
            .where(
                SellerTkRpaTaskPlans.user_id == user_id,
                SellerTkRpaTaskPlans.id == str(task_id).strip(),
            )
            .limit(1)
        )
        existing_task_plan = await self._scalar_one_or_none(session, stmt)
        if existing_task_plan is None:
            self.logger.warning(
                "RPA 任务定向 claim 未命中，数据库中未找到对应任务",
                user_id=user_id,
                task_id=task_id,
                task_type=task_type,
            )
            return

        self.logger.warning(
            "RPA 任务定向 claim 未命中，任务当前不可 claim",
            user_id=user_id,
            task_id=task_id,
            expected_task_type=task_type,
            actual_task_type=existing_task_plan.task_type,
            actual_status=existing_task_plan.status,
            scheduled_time=existing_task_plan.scheduled_time,
            start_time=existing_task_plan.start_time,
            heartbeat_at=existing_task_plan.heartbeat_at,
            last_modifier_id=existing_task_plan.last_modifier_id,
            last_modification_time=existing_task_plan.last_modification_time,
        )

    async def _scalar_one_or_none(
        self,
        session: AsyncSession,
        stmt: Select[tuple[SellerTkRpaTaskPlans]],
    ) -> SellerTkRpaTaskPlans | None:
        result = await session.execute(stmt)
        try:
            return result.scalar_one_or_none()
        finally:
            result.close()

    async def _sync_contract_monitor_log_status(
        self,
        session: AsyncSession,
        *,
        task_plan: SellerTkRpaTaskPlans,
        current_user: CurrentUserInfo,
        utc_now: datetime,
        task_status: SellerRpaTaskStatus,
        normalized_error: str | None,
    ) -> None:
        if str(task_plan.task_type or "").strip().upper() != SellerRpaTaskType.URGE_CHAT.value:
            return
        return
