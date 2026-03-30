from __future__ import annotations

from datetime import datetime, time, timezone
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import and_, select

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.services.task_dispatch_service import (
    SellerRpaTaskDispatchService,
)
from core_base import get_logger
from shared_domain import DatabaseManager
from shared_domain.models.infound import (
    SellerTkRpaTaskPlans,
    SellerTkShopPlatformSettings,
    SellerTkShops,
)


class SellerRpaSampleMonitorPlanService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.scheduler_settings = settings.seller_rpa_scheduler
        self.logger = get_logger(self.__class__.__name__)
        self.dispatch_service = SellerRpaTaskDispatchService(settings)

    async def ensure_daily_plans(self, *, now: datetime | None = None) -> int:
        if not self.scheduler_settings.sample_monitor_daily_enabled:
            return 0

        timezone_name = self.scheduler_settings.sample_monitor_daily_timezone or "Asia/Shanghai"
        local_tz = ZoneInfo(timezone_name)
        utc_now = now or datetime.now(timezone.utc)
        local_now = utc_now.astimezone(local_tz)
        trigger_at_local = datetime.combine(
            local_now.date(),
            time(
                hour=int(self.scheduler_settings.sample_monitor_daily_hour or 1),
                minute=int(self.scheduler_settings.sample_monitor_daily_minute or 10),
            ),
            tzinfo=local_tz,
        )
        if local_now < trigger_at_local:
            return 0

        scheduled_time_utc = trigger_at_local.astimezone(timezone.utc).replace(tzinfo=None)
        task_tabs = list(self.scheduler_settings.sample_monitor_daily_tabs or [])
        created_task_plans: list[SellerTkRpaTaskPlans] = []

        async with DatabaseManager.get_session() as session:
            stmt = (
                select(SellerTkShops)
                .join(
                    SellerTkShopPlatformSettings,
                    and_(
                        SellerTkShopPlatformSettings.region_code == SellerTkShops.shop_region_code,
                        SellerTkShopPlatformSettings.shop_type == SellerTkShops.shop_type,
                        SellerTkShopPlatformSettings.is_active == 1,
                    ),
                )
                .where(SellerTkShops.deleted == 0)
                .order_by(
                    SellerTkShops.user_id.asc(),
                    SellerTkShops.shop_region_code.asc(),
                    SellerTkShops.shop_name.asc(),
                    SellerTkShops.id.asc(),
                )
            )
            shop_result = await session.execute(stmt)
            try:
                shops = shop_result.scalars().all()
            finally:
                shop_result.close()
            for shop in shops:
                task_id = self._build_task_id(shop.user_id, shop.id, local_now.date().isoformat())
                existing_result = await session.execute(
                    select(SellerTkRpaTaskPlans).where(SellerTkRpaTaskPlans.id == task_id)
                )
                try:
                    existing_plan = existing_result.scalar_one_or_none()
                finally:
                    existing_result.close()
                if existing_plan is not None:
                    continue

                task_payload = self._build_task_payload(
                    task_id=task_id,
                    shop=shop,
                    local_date=local_now.date().isoformat(),
                    scheduled_time=scheduled_time_utc,
                    tabs=task_tabs,
                )
                task_plan = SellerTkRpaTaskPlans(
                    id=task_id,
                    user_id=shop.user_id,
                    task_type="SAMPLE_MONITOR",
                    task_payload=task_payload,
                    status="PENDING",
                    scheduled_time=scheduled_time_utc,
                    start_time=None,
                    end_time=None,
                    heartbeat_at=None,
                    error_msg=None,
                    creator_id=shop.user_id,
                    creation_time=utc_now.replace(tzinfo=None),
                    last_modifier_id=shop.user_id,
                    last_modification_time=utc_now.replace(tzinfo=None),
                )
                session.add(task_plan)
                created_task_plans.append(task_plan)

            if created_task_plans:
                await session.commit()

        for task_plan in created_task_plans:
            await self.dispatch_service.schedule_task_plan(task_plan)

        if created_task_plans:
            self.logger.info(
                "样品监控日计划已生成",
                count=len(created_task_plans),
                local_date=local_now.date().isoformat(),
                timezone=timezone_name,
                scheduled_time=scheduled_time_utc.isoformat(),
            )
        return len(created_task_plans)

    @staticmethod
    def _build_task_id(user_id: str, shop_id: str, local_date: str) -> str:
        return str(uuid5(NAMESPACE_URL, f"sample-monitor:{user_id}:{shop_id}:{local_date}")).upper()

    @staticmethod
    def _build_task_payload(
        *,
        task_id: str,
        shop: SellerTkShops,
        local_date: str,
        scheduled_time: datetime,
        tabs: list[str],
    ) -> dict:
        task_name = f"样品监控任务-{local_date}"
        platform_shop_id = str(shop.platform_shop_code or "").strip()
        session_node = {
            "region": str(shop.shop_region_code or "").strip().upper(),
            "headless": False,
        }
        if platform_shop_id:
            session_node["loginStatePath"] = (
                f"%userData%/tk/{shop.user_id}/{shop.id}/{platform_shop_id}.json"
            )
        return {
            "task": {
                "taskId": task_id,
                "taskType": "SAMPLE_MONITOR",
                "taskName": task_name,
                "taskStatus": "PENDING",
                "userId": shop.user_id,
                "shopId": shop.id,
                "shopRegionCode": str(shop.shop_region_code or "").strip().upper(),
                "scheduledTime": scheduled_time.isoformat(),
            },
            "input": {
                "session": session_node,
                "payload": {
                    "taskId": task_id,
                    "taskType": "SAMPLE_MONITOR",
                    "taskName": task_name,
                    "shopId": shop.id,
                    "shopRegionCode": str(shop.shop_region_code or "").strip().upper(),
                    "scheduledTime": scheduled_time.isoformat(),
                    "tabs": tabs,
                },
            },
            "executor": {
                "host": "frontend.desktop",
                "dispatchMode": "user_notification",
                "transport": "rabbitmq_web_stomp",
                "authMode": "jwt",
            },
        }
