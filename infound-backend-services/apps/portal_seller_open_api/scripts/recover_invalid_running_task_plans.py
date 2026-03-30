from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import and_, or_, select

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.services.scheduler_service import SellerRpaSchedulerService
from core_base import SettingsFactory, get_logger
from shared_domain import DatabaseManager
from shared_domain.models.infound import SellerTkRpaTaskPlans


LOGGER = get_logger("recover_invalid_running_task_plans")


async def preview_candidates(
    *,
    scheduler: SellerRpaSchedulerService,
    limit: int,
) -> list[dict[str, str | datetime | None]]:
    timeout_limit = datetime.now(UTC).replace(tzinfo=None) - scheduler.RUNNING_RECOVERY_TIMEOUT
    async with DatabaseManager.get_session() as session:
        stmt = (
            select(SellerTkRpaTaskPlans)
            .where(
                SellerTkRpaTaskPlans.status == "RUNNING",
                SellerTkRpaTaskPlans.task_type.in_(scheduler.SUPPORTED_TASK_TYPES),
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
            .limit(max(int(limit), 1))
        )
        result = await session.execute(stmt)
        try:
            rows = result.scalars().all()
        finally:
            result.close()

    return [
        {
            "task_id": str(row.id),
            "task_type": str(row.task_type or "").strip().upper(),
            "user_id": str(row.user_id or "").strip() or None,
            "scheduled_time": row.scheduled_time,
            "start_time": row.start_time,
            "heartbeat_at": row.heartbeat_at,
            "last_modifier_id": str(row.last_modifier_id or "").strip() or None,
            "last_modification_time": row.last_modification_time,
        }
        for row in rows
    ]


async def main() -> int:
    parser = argparse.ArgumentParser(description="恢复 SellerTkRpaTaskPlans 中异常的 RUNNING 任务")
    parser.add_argument("--dry-run", action="store_true", help="只打印待恢复任务，不执行恢复")
    parser.add_argument("--limit", type=int, default=50, help="dry-run 时最多打印多少条候选任务")
    args = parser.parse_args()

    settings = SettingsFactory.initialize(
        settings_class=Settings,
        config_dir=Path(__file__).resolve().parents[1] / "configs",
    )
    DatabaseManager.initialize(settings.mysql)
    scheduler = SellerRpaSchedulerService(settings)

    try:
        if args.dry_run:
            candidates = await preview_candidates(scheduler=scheduler, limit=args.limit)
            LOGGER.info(
                "异常 RUNNING 任务 dry-run 结果",
                candidate_count=len(candidates),
                tasks=candidates,
            )
            return 0

        recovered = await scheduler._recover_invalid_running_task_plans()
        LOGGER.info("异常 RUNNING 任务恢复执行完成", recovered=recovered)
        return 0
    finally:
        await DatabaseManager.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
