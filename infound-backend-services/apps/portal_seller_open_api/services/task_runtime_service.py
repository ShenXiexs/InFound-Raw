from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
from apps.portal_seller_open_api.services.task_orchestration_service import (
    SellerRpaTaskOrchestrationService,
)
from apps.portal_seller_open_api.services.task_slot_dispatch_service import (
    SellerRpaTaskSingleSlotDispatchService,
)
from core_base import get_logger
from shared_domain import DatabaseManager
from shared_domain.models.infound import (
    IfTkCreators,
    SellerTkOutreachSettings,
    SellerTkOutreachTaskLogs,
    SellerTkRpaTaskPlans,
    SellerTkShops,
)


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
            utc_now = datetime.now(timezone.utc)
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
                task_data=task_plan.task_playload,
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

            utc_now = datetime.now(timezone.utc)
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

            utc_now = datetime.now(timezone.utc)
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

            await session.flush()

            await self._sync_contract_monitor_log_status(
                session,
                task_plan=task_plan,
                current_user=current_user,
                utc_now=utc_now,
                task_status=payload.task_status,
                normalized_error=normalized_error,
            )
            derived_task_plans = await self._sync_outreach_runtime_status(
                session,
                task_plan=task_plan,
                current_user=current_user,
                utc_now=utc_now,
                task_status=payload.task_status,
            )

            await session.commit()

            if derived_task_plans:
                orchestration_service = SellerRpaTaskOrchestrationService(
                    session, self.settings
                )
                await orchestration_service.dispatch_task_plans(derived_task_plans)

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

    async def _sync_outreach_runtime_status(
            self,
            session: AsyncSession,
            *,
            task_plan: SellerTkRpaTaskPlans,
            current_user: CurrentUserInfo,
            utc_now: datetime,
            task_status: SellerRpaTaskStatus,
    ) -> list[SellerTkRpaTaskPlans]:
        normalized_task_type = str(task_plan.task_type or "").strip().upper()
        if normalized_task_type == SellerRpaTaskType.OUTREACH.value:
            await self._sync_outreach_root_runtime_status(
                session,
                task_plan=task_plan,
                current_user=current_user,
                utc_now=utc_now,
                task_status=task_status,
            )
            return []

        if normalized_task_type != SellerRpaTaskType.CHAT.value:
            return []
        if task_status not in {
            SellerRpaTaskStatus.COMPLETED,
            SellerRpaTaskStatus.FAILED,
            SellerRpaTaskStatus.CANCELLED,
        }:
            return []

        task_payload = self._coerce_payload(task_plan.task_playload)
        task_node = self._ensure_record(task_payload.get("task"))
        input_node = self._ensure_record(task_payload.get("input"))
        input_payload = self._ensure_record(input_node.get("payload"))
        root_task_id = (
                clean_text(task_node.get("rootTaskId"))
                or clean_text(input_payload.get("rootTaskId"))
        )
        platform_creator_id = clean_text(input_payload.get("creatorId"))
        if not root_task_id or not platform_creator_id:
            return []

        settings = await self._get_outreach_settings(
            session, current_user.user_id, root_task_id
        )
        if settings is None:
            return []

        current_log = await self._get_outreach_task_log(
            session, root_task_id, platform_creator_id
        )
        if current_log is not None:
            current_log.last_modifier_id = current_user.user_id
            current_log.last_modification_time = utc_now

        completed_chat_count = await self._count_completed_outreach_chat_tasks(
            session, root_task_id
        )
        expect_count = (
            max(0, int(settings.expect_count or 0))
            if settings.expect_count is not None
            else None
        )
        settings.real_count = (
            min(completed_chat_count, expect_count)
            if expect_count is not None
            else completed_chat_count
        )
        settings.last_modifier_id = current_user.user_id
        settings.last_modification_time = utc_now
        normalized_settings_status = str(settings.status or "").strip().upper()
        if normalized_settings_status in {
            SellerRpaTaskStatus.CANCELLED.value,
            "2",
        }:
            if settings.real_end_at is None:
                settings.real_end_at = utc_now
            if not settings.spend_time:
                settings.spend_time = self._duration_seconds(settings.real_start_at, utc_now)
            return []

        next_log = await self._get_next_outreach_task_log(
            session,
            task_id=root_task_id,
            current_log_id=current_log.id if current_log is not None else None,
        )
        if next_log is None:
            settings.status = SellerRpaTaskStatus.COMPLETED.value
            settings.real_end_at = utc_now
            settings.spend_time = self._duration_seconds(settings.real_start_at, utc_now)
            return []

        settings.status = SellerRpaTaskStatus.RUNNING.value
        settings.real_end_at = None

        next_creator = await self._build_outreach_creator_record(
            session, next_log.platform_creator_id
        )
        shop = await self._get_outreach_shop(session, settings.shop_id)
        orchestration_service = SellerRpaTaskOrchestrationService(session, self.settings)
        return await orchestration_service.prepare_outreach_follow_up_tasks_for_creator(
            current_user,
            task_id=root_task_id,
            shop_id=settings.shop_id,
            shop_region_code=clean_text(settings.shop_region_code) or "",
            brand_name=self._resolve_primary_shop_brand_name(shop),
            search_keyword=clean_text(settings.search_keywords),
            message=clean_text(settings.first_message),
            first_message=clean_text(settings.first_message),
            second_message=clean_text(settings.second_message),
            creator=next_creator,
        )

    async def _sync_outreach_root_runtime_status(
            self,
            session: AsyncSession,
            *,
            task_plan: SellerTkRpaTaskPlans,
            current_user: CurrentUserInfo,
            utc_now: datetime,
            task_status: SellerRpaTaskStatus,
    ) -> None:
        if task_status not in {
            SellerRpaTaskStatus.FAILED,
            SellerRpaTaskStatus.CANCELLED,
        }:
            return

        settings = await self._get_outreach_settings(
            session,
            current_user.user_id,
            str(task_plan.id or "").strip(),
        )
        if settings is None:
            return

        settings.status = task_status.value
        settings.real_end_at = utc_now
        settings.spend_time = self._duration_seconds(settings.real_start_at, utc_now)
        settings.last_modifier_id = current_user.user_id
        settings.last_modification_time = utc_now

    async def _count_completed_outreach_chat_tasks(
            self,
            session: AsyncSession,
            root_task_id: str,
    ) -> int:
        log_stmt = (
            select(SellerTkOutreachTaskLogs.platform_creator_id)
            .where(SellerTkOutreachTaskLogs.task_id == root_task_id)
            .order_by(SellerTkOutreachTaskLogs.id.asc())
        )
        creator_ids = list((await session.execute(log_stmt)).scalars().all())
        if not creator_ids:
            return 0

        chat_task_ids = [
            SellerRpaTaskOrchestrationService.build_outreach_chat_task_id(
                root_task_id, str(creator_id)
            )
            for creator_id in creator_ids
        ]
        stmt = select(SellerTkRpaTaskPlans.id).where(
            SellerTkRpaTaskPlans.id.in_(chat_task_ids),
            SellerTkRpaTaskPlans.status == SellerRpaTaskStatus.COMPLETED.value,
        )
        completed_ids = (await session.execute(stmt)).scalars().all()
        return len(completed_ids)

    async def _get_outreach_settings(
            self,
            session: AsyncSession,
            user_id: str,
            task_id: str,
    ) -> SellerTkOutreachSettings | None:
        stmt = (
            select(SellerTkOutreachSettings)
            .where(
                SellerTkOutreachSettings.user_id == user_id,
                SellerTkOutreachSettings.id == task_id,
            )
            .limit(1)
        )
        return await self._scalar_one_or_none(session, stmt)

    async def _get_outreach_task_log(
            self,
            session: AsyncSession,
            task_id: str,
            platform_creator_id: str,
    ) -> SellerTkOutreachTaskLogs | None:
        stmt = (
            select(SellerTkOutreachTaskLogs)
            .where(
                SellerTkOutreachTaskLogs.task_id == task_id,
                SellerTkOutreachTaskLogs.platform_creator_id == platform_creator_id,
            )
            .limit(1)
        )
        result = await session.execute(stmt)
        try:
            return result.scalar_one_or_none()
        finally:
            result.close()

    async def _get_next_outreach_task_log(
        self,
        session: AsyncSession,
        *,
        task_id: str,
        current_log_id: int | None,
    ) -> SellerTkOutreachTaskLogs | None:
        if current_log_id is None:
            return None
        stmt = (
            select(SellerTkOutreachTaskLogs)
            .where(
                SellerTkOutreachTaskLogs.task_id == task_id,
                SellerTkOutreachTaskLogs.id > current_log_id,
            )
            .order_by(SellerTkOutreachTaskLogs.id.asc())
            .limit(1)
        )
        result = await session.execute(stmt)
        try:
            return result.scalar_one_or_none()
        finally:
            result.close()

    async def _build_outreach_creator_record(
            self,
            session: AsyncSession,
            platform_creator_id: str,
    ) -> dict[str, Any]:
        stmt = (
            select(
                IfTkCreators.platform_creator_id,
                IfTkCreators.platform_creator_display_name,
                IfTkCreators.platform_creator_username,
            )
            .where(IfTkCreators.platform_creator_id == platform_creator_id)
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.first()
        result.close()
        creator_name = None
        if row is not None:
            creator_name = clean_text(row.platform_creator_display_name) or clean_text(
                row.platform_creator_username
            )
        return {
            "platform_creator_id": platform_creator_id,
            "creator_name": creator_name or platform_creator_id,
        }

    async def _get_outreach_shop(
            self,
            session: AsyncSession,
            shop_id: str,
    ) -> SellerTkShops | None:
        stmt = select(SellerTkShops).where(SellerTkShops.id == shop_id).limit(1)
        result = await session.execute(stmt)
        try:
            return result.scalar_one_or_none()
        finally:
            result.close()

    @staticmethod
    def _resolve_primary_shop_brand_name(shop: SellerTkShops | None) -> str | None:
        if shop is None:
            return None
        for value in (shop.shop_name, shop.platform_shop_name):
            text = clean_text(value)
            if text:
                return text
        return None

    @staticmethod
    def _duration_seconds(started_at: datetime | None, finished_at: datetime | None) -> int:
        if started_at is None or finished_at is None:
            return 0
        return max(0, int((finished_at - started_at).total_seconds()))

    @staticmethod
    def _coerce_payload(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}

    @staticmethod
    def _ensure_record(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        return {}
