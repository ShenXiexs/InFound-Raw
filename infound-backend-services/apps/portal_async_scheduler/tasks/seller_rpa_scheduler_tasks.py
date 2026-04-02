import time

from apps.portal_async_scheduler.core.config import Settings
from apps.portal_async_scheduler.services.seller_rpa_scheduler_service import (
    SellerRpaSchedulerService,
)
from core_base import SettingsFactory, get_logger

_last_running_recovery_monotonic: float = 0.0


async def run_delayed_dispatch():
    global _last_running_recovery_monotonic
    logger = get_logger(__name__)
    settings = SettingsFactory.get_typed_settings(Settings)
    ss = settings.seller_rpa_scheduler
    if not ss.enabled:
        return

    svc = SellerRpaSchedulerService(settings)
    interval = max(int(ss.running_recovery_interval_seconds or 60), 10)
    now_m = time.monotonic()
    if _last_running_recovery_monotonic <= 0 or (now_m - _last_running_recovery_monotonic) >= interval:
        recovered = await svc.recover_invalid_running_task_plans()
        _last_running_recovery_monotonic = now_m
        if recovered:
            logger.warning("运行中僵尸任务已恢复", recovered=recovered)

    processed = await svc.dispatch_due_delayed_task_plans_once()
    if processed:
        logger.debug("seller_rpa_delayed_dispatch tick handled due tasks")


async def run_sample_monitor_daily():
    logger = get_logger(__name__)
    logger.info("开始执行 seller_rpa_sample_monitor_daily")

    settings = SettingsFactory.get_typed_settings(Settings)
    ss = settings.seller_rpa_scheduler
    if not ss.enabled or not ss.sample_monitor_daily_enabled:
        logger.info("结束执行 seller_rpa_sample_monitor_daily")
        return

    svc = SellerRpaSchedulerService(settings)
    created = await svc.ensure_sample_monitor_daily_plans()
    if created:
        logger.info("样品监控日计划已由调度器生成", count=created)
    else:
        logger.info(
            "样品监控日计划本轮未插入新行",
            reason_hint=(
                "未到 seller_rpa_scheduler 配置的当日触发时刻；或当日计划已存在；或库中无符合 JOIN 条件的店铺"
            ),
            sample_monitor_daily_hour=ss.sample_monitor_daily_hour,
            sample_monitor_daily_minute=ss.sample_monitor_daily_minute,
            sample_monitor_daily_timezone=ss.sample_monitor_daily_timezone,
        )

    logger.info("结束执行 seller_rpa_sample_monitor_daily")
