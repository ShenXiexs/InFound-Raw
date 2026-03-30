from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.services.task_dispatch_service import (
    SellerRpaTaskDispatchService,
)
from apps.portal_seller_open_api.services.task_notification_service import (
    SellerRpaTaskNotificationResult,
    SellerRpaTaskNotificationService,
)
from core_base import get_logger
from shared_domain.models.infound import SellerTkRpaTaskPlans


@dataclass(frozen=True)
class SellerRpaSingleSlotDispatchResult:
    dispatched: bool
    slot_busy: bool = False
    reason: str | None = None
    task_id: str | None = None
    notification_result: SellerRpaTaskNotificationResult | None = None


class SellerRpaTaskSingleSlotDispatchService:
    RUNNING_STATUS = "RUNNING"
    PENDING_STATUS = "PENDING"

    def __init__(self, db_session: AsyncSession, settings: Settings) -> None:
        self.db_session = db_session
        self.settings = settings
        self.logger = get_logger(self.__class__.__name__)
        self.notification_service = SellerRpaTaskNotificationService(settings)
        self.dispatch_service = SellerRpaTaskDispatchService(settings)

    async def dispatch_if_slot_available(
        self,
        task_plan: SellerTkRpaTaskPlans,
        *,
        payload: dict | None = None,
        schedule_retry_on_busy: bool = True,
    ) -> SellerRpaSingleSlotDispatchResult:
        normalized_task_type = str(task_plan.task_type or "").strip().upper()
        normalized_user_id = str(task_plan.user_id or "").strip()
        normalized_task_id = str(task_plan.id or "").strip()
        normalized_status = str(task_plan.status or "").strip().upper()

        if not normalized_user_id or not normalized_task_type or not normalized_task_id:
            return SellerRpaSingleSlotDispatchResult(
                dispatched=False,
                reason="invalid-task-plan",
                task_id=normalized_task_id or None,
            )

        if normalized_status != self.PENDING_STATUS:
            return SellerRpaSingleSlotDispatchResult(
                dispatched=False,
                reason=f"task-status-{normalized_status.lower() or 'unknown'}",
                task_id=normalized_task_id,
            )

        if await self.has_running_task(
            user_id=normalized_user_id,
            task_type=normalized_task_type,
            exclude_task_id=normalized_task_id,
        ):
            if schedule_retry_on_busy:
                await self.dispatch_service.schedule_task_plan(task_plan)
            return SellerRpaSingleSlotDispatchResult(
                dispatched=False,
                slot_busy=True,
                reason="slot-busy",
                task_id=normalized_task_id,
            )

        publish_result = await self.dispatch_service.try_publish_task_plan(task_plan)
        if not publish_result.published:
            return SellerRpaSingleSlotDispatchResult(
                dispatched=False,
                reason=publish_result.reason,
                task_id=normalized_task_id,
            )

        notification_result = await self.notification_service.notify_task_ready(
            task_plan,
            payload=payload or {},
        )
        if notification_result.notified:
            return SellerRpaSingleSlotDispatchResult(
                dispatched=True,
                reason="notified",
                task_id=normalized_task_id,
                notification_result=notification_result,
            )

        await self.dispatch_service.clear_task_plan(normalized_task_id, normalized_task_type)
        await self.dispatch_service.schedule_task_plan(task_plan)
        return SellerRpaSingleSlotDispatchResult(
            dispatched=False,
            reason=notification_result.reason or "notify-failed",
            task_id=normalized_task_id,
            notification_result=notification_result,
        )

    async def dispatch_next_pending_task(
        self,
        *,
        user_id: str,
        task_type: str,
    ) -> SellerRpaSingleSlotDispatchResult:
        normalized_user_id = str(user_id or "").strip()
        normalized_task_type = str(task_type or "").strip().upper()
        if not normalized_user_id or not normalized_task_type:
            return SellerRpaSingleSlotDispatchResult(
                dispatched=False,
                reason="invalid-slot",
            )

        if await self.has_running_task(
            user_id=normalized_user_id,
            task_type=normalized_task_type,
        ):
            return SellerRpaSingleSlotDispatchResult(
                dispatched=False,
                slot_busy=True,
                reason="slot-busy",
            )

        stmt = (
            select(SellerTkRpaTaskPlans)
            .where(
                SellerTkRpaTaskPlans.user_id == normalized_user_id,
                SellerTkRpaTaskPlans.task_type == normalized_task_type,
                SellerTkRpaTaskPlans.status == self.PENDING_STATUS,
                SellerTkRpaTaskPlans.scheduled_time <= datetime.utcnow(),
            )
            .order_by(
                SellerTkRpaTaskPlans.scheduled_time.asc(),
                SellerTkRpaTaskPlans.creation_time.asc(),
                SellerTkRpaTaskPlans.id.asc(),
            )
            .limit(1)
        )
        task_plan = await self._scalar_one_or_none(stmt)
        if task_plan is None:
            return SellerRpaSingleSlotDispatchResult(
                dispatched=False,
                reason="no-pending-task",
            )

        return await self.dispatch_if_slot_available(task_plan)

    async def has_running_task(
        self,
        *,
        user_id: str,
        task_type: str,
        exclude_task_id: str | None = None,
    ) -> bool:
        stmt = select(SellerTkRpaTaskPlans.id).where(
            SellerTkRpaTaskPlans.user_id == str(user_id).strip(),
            SellerTkRpaTaskPlans.task_type == str(task_type).strip().upper(),
            SellerTkRpaTaskPlans.status == self.RUNNING_STATUS,
        )
        normalized_exclude_task_id = str(exclude_task_id or "").strip()
        if normalized_exclude_task_id:
            stmt = stmt.where(SellerTkRpaTaskPlans.id != normalized_exclude_task_id)
        stmt = stmt.limit(1)
        result = await self.db_session.execute(stmt)
        try:
            return result.scalar_one_or_none() is not None
        finally:
            result.close()

    async def _scalar_one_or_none(
        self, stmt: Select[tuple[SellerTkRpaTaskPlans]]
    ) -> SellerTkRpaTaskPlans | None:
        result = await self.db_session.execute(stmt)
        try:
            return result.scalar_one_or_none()
        finally:
            result.close()
