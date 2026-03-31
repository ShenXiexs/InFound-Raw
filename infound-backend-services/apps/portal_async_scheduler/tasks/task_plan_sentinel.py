from datetime import datetime, timedelta

from sqlalchemy import update, func, select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core_base import get_logger
from shared_domain import DatabaseManager
from shared_domain.models.infound import SellerTkRpaTaskPlans


class SentinelService:
    def __init__(self, db: AsyncSession):
        self.logger = get_logger(__name__)
        self.db = db

    async def patrol(self):
        """哨兵巡逻主函数"""
        await self._recover_zombie_tasks()
        await self._expire_old_pending_tasks()
        await self._cleanup_monitor_accumulation()

    async def _recover_zombie_tasks(self):
        """1. 回收僵尸任务：心跳超时 5 分钟"""
        utc_now = datetime.now()
        timeout_limit = utc_now - timedelta(minutes=5)

        # 找出那些断了气（心跳超时）的任务
        stmt = (
            update(SellerTkRpaTaskPlans)
            .where(SellerTkRpaTaskPlans.status == 'RUNNING')
            .where(
                or_(
                    SellerTkRpaTaskPlans.heartbeat_at < timeout_limit,
                    and_(
                        SellerTkRpaTaskPlans.heartbeat_at.is_(None),
                        SellerTkRpaTaskPlans.last_modification_time < timeout_limit,
                    ),
                )
            )
            .values(
                status='PENDING',
                start_time=None,
                end_time=None,
                heartbeat_at=None,
                error_msg="Sentinel: Heartbeat timeout or missing heartbeat, task reverted.",
                last_modification_time=utc_now,
            )
        )
        result = await self.db.execute(stmt)
        if result.rowcount > 0:
            self.logger.warning("哨兵：回收了僵尸任务", recovered=result.rowcount)
        await self.db.commit()

    async def _expire_old_pending_tasks(self):
        """2. 清理过期任务：超过 24 小时没人领"""
        expiry_limit = datetime.now() - timedelta(hours=24)

        stmt = (
            update(SellerTkRpaTaskPlans)
            .where(SellerTkRpaTaskPlans.status == 'PENDING')
            .where(SellerTkRpaTaskPlans.scheduled_time < expiry_limit)
            .values(status='failed', error_msg="Sentinel: Task expired (Client offline too long).")
        )
        await self.db.execute(stmt)
        await self.db.commit()

    async def _cleanup_monitor_accumulation(self):
        """3. 堆积清理：同一个用户同一个 Slot 积压超过 3 个 MONITOR 任务，只留最新的"""
        # 这种逻辑通常用于样品监控，昨天的没跑，今天跑最新的就行
        # 找出每个用户每种任务类型中 scheduled_time 最大的 ID（要保留的）
        max_time_subq = (
            select(
                SellerTkRpaTaskPlans.user_id,
                SellerTkRpaTaskPlans.task_type,
                func.max(SellerTkRpaTaskPlans.scheduled_time).label('max_time')
            )
            .where(
                SellerTkRpaTaskPlans.status == 'PENDING',
                SellerTkRpaTaskPlans.task_type == 'SAMPLE_MONITOR'
            )
            .group_by(SellerTkRpaTaskPlans.user_id, SellerTkRpaTaskPlans.task_type)
            .having(func.count(SellerTkRpaTaskPlans.id) > 1)
        ).alias('max_times')

        # 更新：将不是最新时间的任务设为 EXPIRED
        stmt = (
            update(SellerTkRpaTaskPlans)
            .where(
                SellerTkRpaTaskPlans.status == 'PENDING',
                SellerTkRpaTaskPlans.task_type == 'SAMPLE_MONITOR',
                SellerTkRpaTaskPlans.user_id.in_(select(max_time_subq.c.user_id)),
                SellerTkRpaTaskPlans.scheduled_time < max_time_subq.c.max_time
            )
            .values(
                status='EXPIRED',
                error_msg="Sentinel: Cleaned up accumulated monitoring task."
            )
        )

        result = await self.db.execute(stmt)
        if result.rowcount > 0:
            self.logger.info(f"哨兵：清理了 {result.rowcount} 个堆积的监控任务")
        await self.db.commit()


async def run():
    logger = get_logger(__name__)

    logger.info("开始执行 task_plan_sentinel")

    async with DatabaseManager.get_session() as db:
        sentinel = SentinelService(db)
        await sentinel.patrol()

    logger.info("结束执行 task_plan_sentinel")
