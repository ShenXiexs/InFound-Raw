"""
任务管理路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pathlib import Path
from datetime import datetime
import json
import uuid
import sqlite3
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ..database import get_db
from ..models.user import User
from ..auth.dependencies import get_current_user
from ..schemas import TaskSubmitRequest, TaskSubmitResponse, TaskStatusResponse, TaskListResponse
from ..config import settings

# 导入现有的任务管理器和账号池
from crawler.parallel_manager import ParallelTaskManager
from models.account_pool import get_account_pool

router = APIRouter(prefix="/api/tasks", tags=["任务管理"])

# 全局任务管理器（延迟初始化）
task_manager = None


def get_or_create_manager():
    """获取或创建全局任务管理器"""
    global task_manager

    if task_manager is None:
        task_manager = ParallelTaskManager(
            max_workers=settings.MAX_WORKERS,
            db_path=settings.CRAWLER_DB_PATH,
            account_pool_config=settings.ACCOUNT_POOL_CONFIG,
        )

        # 启动 Worker 进程
        for i in range(1):  # 至少启动 1 个 Worker
            worker_id = f"worker_{i}"
            task_manager.start_worker(worker_id)

        # 启动管理器监控线程
        import threading

        def run_manager():
            try:
                task_manager.run(daemon=True)
            except Exception as e:
                print(f"任务管理器异常: {e}")

        threading.Thread(target=run_manager, daemon=True, name="TaskManagerThread").start()

    return task_manager


def validate_task_config(data: dict):
    """验证前端传来的配置是否完整"""
    required_fields = ["region", "brand", "search_strategy", "email_first", "email_later"]

    for field in required_fields:
        if field not in data:
            return False, f"缺少必需字段: {field}"

    if "name" not in data["brand"]:
        return False, "brand.name 不能为空"

    if not isinstance(data["search_strategy"], dict):
        return False, "search_strategy 必须是对象"

    return True, None


@router.post("/submit", response_model=TaskSubmitResponse, status_code=201)
async def submit_task(
    task_data: TaskSubmitRequest,
    current_user: User = Depends(get_current_user),
):
    """
    提交爬虫任务

    需要登录才能访问。

    - **region**: 区域 (如: FR, MX)
    - **brand**: 品牌配置
    - **search_strategy**: 搜索策略配置
    - **email_first**: 首次邮箱验证配置
    - **email_later**: 后续邮箱验证配置
    """
    try:
        # 转换为字典
        data = task_data.model_dump()

        # 验证配置
        is_valid, error_msg = validate_task_config(data)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        # 检查账号池
        pool = get_account_pool()
        region = data.get("region", "").upper()

        status_info = pool.get_status()
        has_region_account = any(
            acc["region"].upper() == region
            for acc in status_info["accounts"]
            if acc.get("enabled", True)
        )

        if not has_region_account:
            raise HTTPException(status_code=400, detail=f"没有可用的 {region} 区域账号")

        # 生成任务ID
        brand_name = data["brand"]["name"]
        task_id = f"{brand_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # 创建任务目录
        task_dir = Path(f"data/tasks/{brand_name}/{task_id}")
        task_dir.mkdir(parents=True, exist_ok=True)

        # 保存配置文件
        config_file = task_dir / "dify_out.txt"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 准备任务配置
        task_config = {
            "name": task_id,
            "source_dir": str(task_dir),
            "config_files": [{"file": str(config_file), "name": task_id, "data": data}],
            "config_count": 1,
            "_product_group": brand_name,
        }

        # 提交任务到管理器
        manager = get_or_create_manager()
        submitted_task_id = manager.add_task(task_config, str(config_file))

        return TaskSubmitResponse(
            task_id=submitted_task_id,
            brand_name=brand_name,
            region=region,
            status="pending",
            message="任务已提交到队列",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    查询任务状态

    需要登录才能访问。
    """
    try:
        with sqlite3.connect(settings.CRAWLER_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT task_id, task_name, status, start_time, end_time, total_creators
                FROM tasks WHERE task_id = ?
            """,
                (task_id,),
            )

            row = cursor.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="任务不存在")

            return TaskStatusResponse(
                task_id=row[0],
                task_name=row[1],
                status=row[2],
                start_time=row[3],
                end_time=row[4],
                total_creators=row[5],
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=TaskListResponse)
async def list_tasks(
    status_filter: str = Query(None, description="过滤状态 (pending/running/completed/failed)"),
    limit: int = Query(100, description="返回数量限制"),
    current_user: User = Depends(get_current_user),
):
    """
    列出所有任务

    需要登录才能访问。

    - **status**: 过滤状态 (可选)
    - **limit**: 返回数量限制 (默认100)
    """
    try:
        with sqlite3.connect(settings.CRAWLER_DB_PATH) as conn:
            cursor = conn.cursor()

            if status_filter:
                cursor.execute(
                    """
                    SELECT task_id, task_name, status, start_time, end_time, total_creators
                    FROM tasks WHERE status = ? ORDER BY start_time DESC LIMIT ?
                """,
                    (status_filter, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT task_id, task_name, status, start_time, end_time, total_creators
                    FROM tasks ORDER BY start_time DESC LIMIT ?
                """,
                    (limit,),
                )

            rows = cursor.fetchall()

            tasks = [
                TaskStatusResponse(
                    task_id=row[0],
                    task_name=row[1],
                    status=row[2],
                    start_time=row[3],
                    end_time=row[4],
                    total_creators=row[5],
                )
                for row in rows
            ]

            return TaskListResponse(tasks=tasks, total=len(tasks))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cancel/{task_id}")
async def cancel_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    取消任务

    需要登录才能访问。
    """
    try:
        with sqlite3.connect(settings.CRAWLER_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tasks SET status = 'cancelled'
                WHERE task_id = ? AND status IN ('pending', 'running')
            """,
                (task_id,),
            )
            conn.commit()

            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="任务不存在或已完成")

            return {"success": True, "message": "任务已标记为取消"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
