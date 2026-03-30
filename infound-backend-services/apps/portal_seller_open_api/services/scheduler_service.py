from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import and_, or_, select

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.services.task_dispatch_service import (
    SellerRpaTaskDispatchService,
)
from apps.portal_seller_open_api.services.task_slot_dispatch_service import (
    SellerRpaTaskSingleSlotDispatchService,
)
from apps.portal_seller_open_api.services.sample_monitor_plan_service import (
    SellerRpaSampleMonitorPlanService,
)
from core_base import get_logger
from shared_domain import DatabaseManager
from shared_domain.models.infound import SellerTkRpaTaskPlans


class SellerRpaSchedulerService:
    SUPPORTED_TASK_TYPES = (
        "OUTREACH",
        "CREATOR_DETAIL",
        "CHAT",
        "SAMPLE_MONITOR",
        "URGE_CHAT",
    )
    RUNNING_RECOVERY_TIMEOUT = timedelta(minutes=5)

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.scheduler_settings = settings.seller_rpa_scheduler
        self.logger = get_logger(self.__class__.__name__)
        self.dispatch_service = SellerRpaTaskDispatchService(settings)
        self.sample_monitor_plan_service = SellerRpaSampleMonitorPlanService(settings)
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._running_recovery_interval_seconds = max(
            int(getattr(self.scheduler_settings, "running_recovery_interval_seconds", 60) or 60),
            10,
        )
        self._last_running_recovery_at = 0.0

    async def start(self) -> None:
        if not self.scheduler_settings.enabled:
            self.logger.info("Seller RPA scheduler 已禁用，跳过启动")
            return
        if self._tasks:
            return

        recovered_running = await self._recover_invalid_running_task_plans()
        await self._recover_pending_task_plans()
        self._last_running_recovery_at = time.monotonic()

        self._stop_event.clear()
        self._tasks = [
            asyncio.create_task(self._run_delayed_dispatch_loop()),
            asyncio.create_task(self._run_sample_monitor_daily_plan_loop()),
        ]
        self.logger.info(
            "Seller RPA scheduler 已启动",
            delayed_poll_interval_seconds=self.scheduler_settings.delayed_poll_interval_seconds,
            recovered_running=recovered_running,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        self.logger.info("Seller RPA scheduler 已停止")

    async def _run_delayed_dispatch_loop(self) -> None:
        interval = max(int(self.scheduler_settings.delayed_poll_interval_seconds or 5), 1)
        while not self._stop_event.is_set():
            try:
                if self._should_run_running_recovery():
                    recovered_running = await self._recover_invalid_running_task_plans()
                    self._last_running_recovery_at = time.monotonic()
                    if recovered_running:
                        self.logger.warning(
                            "运行中僵尸任务已恢复",
                            recovered=recovered_running,
                        )
                processed = await self._dispatch_due_task_plans_once()
                if not processed:
                    await self._sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger.error("延迟任务调度器执行异常", exc_info=True)
                await self._sleep(interval)

    async def _run_sample_monitor_daily_plan_loop(self) -> None:
        interval = max(int(self.scheduler_settings.sample_monitor_daily_check_interval_seconds or 60), 10)
        while not self._stop_event.is_set():
            try:
                await self.sample_monitor_plan_service.ensure_daily_plans()
                await self._sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger.error("样品监控日计划生成异常", exc_info=True)
                await self._sleep(interval)

    async def _recover_pending_task_plans(self) -> None:
        now = datetime.utcnow()
        batch_size = max(int(self.scheduler_settings.recovery_batch_size or 500), 1)
        async with DatabaseManager.get_session() as session:
            stmt = (
                select(SellerTkRpaTaskPlans)
                .where(
                    SellerTkRpaTaskPlans.status == "PENDING",
                    SellerTkRpaTaskPlans.task_type.in_(self.SUPPORTED_TASK_TYPES),
                )
                .order_by(SellerTkRpaTaskPlans.scheduled_time.asc())
                .limit(batch_size)
            )
            result = await session.execute(stmt)
            try:
                task_plans = result.scalars().all()
            finally:
                result.close()

        recovered = 0
        for task_plan in task_plans:
            await self.dispatch_service.schedule_task_plan(task_plan)
            recovered += 1
            if task_plan.scheduled_time <= now and not await self.dispatch_service.has_dispatch_marker(
                task_plan.id
            ):
                try:
                    async with DatabaseManager.get_session() as dispatch_session:
                        dispatch_stmt = (
                            select(SellerTkRpaTaskPlans)
                            .where(SellerTkRpaTaskPlans.id == task_plan.id)
                            .limit(1)
                        )
                        dispatch_result = await dispatch_session.execute(dispatch_stmt)
                        try:
                            live_task_plan = dispatch_result.scalar_one_or_none()
                        finally:
                            dispatch_result.close()

                        if live_task_plan is None or live_task_plan.status != "PENDING":
                            continue

                        slot_dispatch_service = SellerRpaTaskSingleSlotDispatchService(
                            dispatch_session, self.settings
                        )
                        dispatch_outcome = await slot_dispatch_service.dispatch_if_slot_available(
                            live_task_plan,
                            payload={},
                        )
                        if dispatch_outcome.dispatched:
                            self.logger.info(
                                "启动恢复时任务已激活并通知客户端",
                                task_id=live_task_plan.id,
                                task_type=live_task_plan.task_type,
                                notified=True,
                                routing_key=dispatch_outcome.notification_result.routing_key
                                if dispatch_outcome.notification_result
                                else None,
                                reason=dispatch_outcome.reason,
                            )
                except Exception:
                    self.logger.error(
                        "启动恢复时投递任务失败，等待调度器后续重试",
                        task_id=task_plan.id,
                        task_type=task_plan.task_type,
                        exc_info=True,
                    )
        self.logger.info("Seller RPA scheduler 已恢复待调度任务", recovered=recovered)

    async def _recover_invalid_running_task_plans(self) -> int:
        now = datetime.utcnow()
        timeout_limit = now - self.RUNNING_RECOVERY_TIMEOUT
        batch_size = max(int(self.scheduler_settings.recovery_batch_size or 500), 1)

        async with DatabaseManager.get_session() as session:
            stmt = (
                select(SellerTkRpaTaskPlans)
                .where(
                    SellerTkRpaTaskPlans.status == "RUNNING",
                    SellerTkRpaTaskPlans.task_type.in_(self.SUPPORTED_TASK_TYPES),
                    or_(
                        SellerTkRpaTaskPlans.heartbeat_at < timeout_limit,
                        and_(
                            SellerTkRpaTaskPlans.heartbeat_at.is_(None),
                            SellerTkRpaTaskPlans.last_modification_time < timeout_limit,
                        ),
                    ),
                )
                .order_by(
                    SellerTkRpaTaskPlans.last_modification_time.asc(),
                    SellerTkRpaTaskPlans.creation_time.asc(),
                    SellerTkRpaTaskPlans.id.asc(),
                )
                .limit(batch_size)
            )
            result = await session.execute(stmt)
            try:
                task_plans = result.scalars().all()
            finally:
                result.close()

            if not task_plans:
                return 0

            recovered_tasks: list[dict[str, str | datetime | None]] = []
            for task_plan in task_plans:
                had_heartbeat = task_plan.heartbeat_at is not None
                previous_last_modifier_id = str(task_plan.last_modifier_id or "").strip() or None
                previous_last_modification_time = task_plan.last_modification_time
                task_plan.status = "PENDING"
                task_plan.start_time = None
                task_plan.end_time = None
                task_plan.heartbeat_at = None
                recovery_reason = (
                    "Scheduler recovery: heartbeat timeout"
                    if had_heartbeat
                    else "Scheduler recovery: running task missing heartbeat"
                )
                existing_error = str(task_plan.error_msg or "").strip()
                task_plan.error_msg = (
                    f"{recovery_reason}; previous_error={existing_error}"
                    if existing_error
                    else recovery_reason
                )
                task_plan.last_modification_time = now
                recovered_tasks.append(
                    {
                        "task_id": str(task_plan.id),
                        "task_type": str(task_plan.task_type or "").strip().upper(),
                        "scheduled_time": task_plan.scheduled_time,
                        "previous_last_modifier_id": previous_last_modifier_id,
                        "previous_last_modification_time": previous_last_modification_time,
                    }
                )

            await session.commit()

        for recovered_task in recovered_tasks:
            task_id = str(recovered_task["task_id"] or "").strip()
            task_type = str(recovered_task["task_type"] or "").strip().upper()
            scheduled_time = recovered_task["scheduled_time"]
            if not task_id or not task_type or not isinstance(scheduled_time, datetime):
                continue
            await self.dispatch_service.clear_task_plan(task_id, task_type)
            await self.dispatch_service.schedule_task_plan(
                SimpleNamespace(
                    id=task_id,
                    task_type=task_type,
                    scheduled_time=scheduled_time,
                )
            )

        self.logger.warning(
            "Seller RPA scheduler 恢复了异常 RUNNING 任务计划",
            recovered=len(recovered_tasks),
            tasks=recovered_tasks[:20],
        )
        return len(recovered_tasks)

    async def _dispatch_due_task_plans_once(self) -> bool:
        now = datetime.utcnow()
        batch_size = max(int(self.scheduler_settings.delayed_batch_size or 50), 1)
        processed = False

        for task_type in self.SUPPORTED_TASK_TYPES:
            task_ids = await self.dispatch_service.get_due_task_ids(
                task_type,
                now=now,
                batch_size=batch_size,
            )
            for task_id in task_ids:
                try:
                    async with DatabaseManager.get_session() as session:
                        stmt = (
                            select(SellerTkRpaTaskPlans)
                            .where(SellerTkRpaTaskPlans.id == task_id)
                            .limit(1)
                        )
                        query_result = await session.execute(stmt)
                        try:
                            task_plan = query_result.scalar_one_or_none()
                        finally:
                            query_result.close()

                        if task_plan is None or task_plan.status != "PENDING":
                            await self.dispatch_service.clear_task_plan(task_id, task_type)
                            processed = True
                            continue

                        slot_dispatch_service = SellerRpaTaskSingleSlotDispatchService(
                            session, self.settings
                        )
                        result = await slot_dispatch_service.dispatch_if_slot_available(
                            task_plan,
                            payload={},
                        )
                        if result.dispatched:
                            processed = True
                            self.logger.info(
                                "到期任务已激活并通知客户端",
                                task_id=task_plan.id,
                                task_type=task_plan.task_type,
                                reason=result.reason,
                                notified=True,
                                routing_key=result.notification_result.routing_key
                                if result.notification_result
                                else None,
                                notify_reason=result.notification_result.reason
                                if result.notification_result
                                else None,
                            )
                        elif result.slot_busy:
                            processed = True
                except Exception:
                    processed = True
                    self.logger.error(
                        "到期任务投递失败，等待调度器后续重试",
                        task_id=task_id,
                        task_type=task_type,
                        exc_info=True,
                    )
        return processed

    async def _sleep(self, seconds: int) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    def _should_run_running_recovery(self) -> bool:
        if self._last_running_recovery_at <= 0:
            return True
        return (time.monotonic() - self._last_running_recovery_at) >= self._running_recovery_interval_seconds
