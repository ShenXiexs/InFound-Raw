from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.services.task_dispatch_service import (
    SellerRpaTaskDispatchService,
)
from apps.portal_seller_open_api.services.task_notification_service import (
    SellerRpaTaskNotificationService,
)
from core_base import get_logger
from shared_domain import DatabaseManager
from shared_domain.models.infound import SellerTkRpaTaskPlans


class SellerRpaSchedulerService:
    SUPPORTED_TASK_TYPES = ("OUTREACH", "CREATOR_DETAIL", "CHAT", "SAMPLE_MONITOR")

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.scheduler_settings = settings.seller_rpa_scheduler
        self.logger = get_logger(self.__class__.__name__)
        self.dispatch_service = SellerRpaTaskDispatchService(settings)
        self.notification_service = SellerRpaTaskNotificationService(settings)
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        if not self.scheduler_settings.enabled:
            self.logger.info("Seller RPA scheduler 已禁用，跳过启动")
            return
        if self._tasks:
            return

        await self._recover_pending_task_plans()

        self._stop_event.clear()
        self._tasks = [asyncio.create_task(self._run_delayed_dispatch_loop())]
        self.logger.info(
            "Seller RPA scheduler 已启动",
            delayed_poll_interval_seconds=self.scheduler_settings.delayed_poll_interval_seconds,
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
                processed = await self._dispatch_due_task_plans_once()
                if not processed:
                    await self._sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception:
                self.logger.error("延迟任务调度器执行异常", exc_info=True)
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
            task_plans = (await session.execute(stmt)).scalars().all()

        recovered = 0
        for task_plan in task_plans:
            await self.dispatch_service.schedule_task_plan(task_plan)
            recovered += 1
            if task_plan.scheduled_time <= now and not await self.dispatch_service.has_dispatch_marker(
                task_plan.id
            ):
                try:
                    result = await self.dispatch_service.try_publish_task_plan(task_plan)
                    if result.published:
                        notification_result = await self.notification_service.notify_task_ready(
                            task_plan,
                            payload={},
                        )
                        self.logger.info(
                            "启动恢复时任务已激活并通知客户端",
                            task_id=task_plan.id,
                            task_type=task_plan.task_type,
                            notified=notification_result.notified,
                            routing_key=notification_result.routing_key,
                            reason=notification_result.reason,
                        )
                except Exception:
                    self.logger.error(
                        "启动恢复时投递任务失败，等待调度器后续重试",
                        task_id=task_plan.id,
                        task_type=task_plan.task_type,
                        exc_info=True,
                    )
        self.logger.info("Seller RPA scheduler 已恢复待调度任务", recovered=recovered)

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
                async with DatabaseManager.get_session() as session:
                    stmt = select(SellerTkRpaTaskPlans).where(
                        SellerTkRpaTaskPlans.id == task_id
                    )
                    task_plan = (await session.execute(stmt)).scalar_one_or_none()
                    if task_plan is None or task_plan.status != "PENDING":
                        await self.dispatch_service.clear_task_plan(task_id, task_type)
                        processed = True
                        continue

                try:
                    result = await self.dispatch_service.try_publish_task_plan(task_plan)
                    if result.published:
                        processed = True
                        notification_result = await self.notification_service.notify_task_ready(
                            task_plan,
                            payload={},
                        )
                        self.logger.info(
                            "到期任务已激活并通知客户端",
                            task_id=task_plan.id,
                            task_type=task_plan.task_type,
                            reason=result.reason,
                            notified=notification_result.notified,
                            routing_key=notification_result.routing_key,
                            notify_reason=notification_result.reason,
                        )
                except Exception:
                    processed = True
                    self.logger.error(
                        "到期任务投递失败，等待调度器后续重试",
                        task_id=task_plan.id,
                        task_type=task_plan.task_type,
                        exc_info=True,
                    )
        return processed

    async def _sleep(self, seconds: int) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return
