"""
爬虫服务封装
"""
from __future__ import annotations

import logging
from threading import Lock
from datetime import datetime
from typing import List, Optional, Tuple

from core.config import settings
from crawler.parallel_manager import ParallelTaskManager
from models.account_pool import get_account_pool
from database.outreach_tasks_repo import (
    get_task_status as get_persisted_task_status,
    list_tasks as list_persisted_tasks,
)
from schemas.crawler import (
    CrawlerSummaryResponse,
    CrawlerTaskCreateRequest,
    CrawlerTaskStatus,
    CrawlerTaskUpdateRequest,
    CrawlerTaskRenameRequest,
)

logger = logging.getLogger(__name__)


class CrawlerService:
    """面向API的爬虫服务，封装底层任务管理器。"""

    def __init__(self) -> None:
        account_pool = get_account_pool(settings.ACCOUNT_CONFIG_PATH)
        total_accounts = account_pool.get_total_count()
        max_workers = max(
            1,
            settings.MAX_CONCURRENT_TASKS,
            getattr(settings, "MAX_WORKERS", 1),
            total_accounts or 1,
        )
        self._manager = ParallelTaskManager(
            max_workers=max_workers,
            task_root=settings.TASK_DIR,
            task_data_dir=settings.TASK_DATA_DIR,
            account_pool_config=settings.ACCOUNT_CONFIG_PATH,
            task_timeout_minutes=settings.TASK_TIMEOUT_MINUTES,
        )
        logger.info(
            "CrawlerService 初始化: max_workers=%s, 账号总数=%s (允许账号共享)",
            max_workers,
            total_accounts,
        )

    def submit_task(
        self,
        request: CrawlerTaskCreateRequest,
        created_by: str,
    ) -> str:
        """创建并提交任务到任务管理器."""
        return self._manager.submit_task(request, created_by)

    def list_tasks(
        self,
        *,
        brand_name: Optional[str] = None,
        region: Optional[str] = None,
        status: Optional[str] = None,
        task_name: Optional[str] = None,
        run_at_time: Optional[datetime] = None,
        run_end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20,
        sort: Optional[str] = None,
    ) -> Tuple[List[CrawlerTaskStatus], int]:
        """按条件过滤并分页返回任务列表。"""
        persisted, total = list_persisted_tasks(
            brand_name=brand_name,
            region=region,
            status=status,
            task_name=task_name,
            run_at_time=run_at_time,
            run_end_time=run_end_time,
            page=page,
            page_size=page_size,
            sort=sort,
        )

        merged: List[CrawlerTaskStatus] = []
        for task in persisted:
            active = self._manager.get_task(task.task_id)
            merged.append(active or task)
        return merged, total

    def get_task(self, task_id: str) -> Optional[CrawlerTaskStatus]:
        """获取单个任务的状态。"""
        task = self._manager.get_task(task_id)
        if task:
            return task
        return get_persisted_task_status(task_id)

    def update_task(self, task_id: str, update_request: CrawlerTaskUpdateRequest) -> None:
        """更新尚未执行的任务配置。"""
        self._manager.update_task(task_id, update_request)

    def rename_task(self, task_id: str, rename_request: CrawlerTaskRenameRequest) -> None:
        self._manager.update_task_name(task_id, rename_request.task_name)

    def cancel_task(self, task_id: str) -> bool:
        """取消仍在排队的任务。"""
        return self._manager.cancel_task(task_id)

    def run_task_now(self, task_id: str) -> None:
        """将计划任务立即执行。"""
        self._manager.run_task_now(task_id)

    def get_summary(self) -> CrawlerSummaryResponse:
        """返回任务队列的统计信息。"""
        return self._manager.get_summary()

    def force_cancel_task(self, task_id: str) -> bool:
        """强制终止任务。"""
        return self._manager.force_cancel_task(task_id)


_service_instance: Optional[CrawlerService] = None
_service_lock = Lock()


def get_crawler_service() -> CrawlerService:
    """获取单例服务实例，避免多次初始化执行器。"""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                logger.info("初始化 CrawlerService 实例")
                _service_instance = CrawlerService()
    return _service_instance
