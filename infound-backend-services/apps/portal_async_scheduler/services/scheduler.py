# 加载任务配置
import importlib
from pathlib import Path

import structlog
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from ruamel.yaml import YAML

from apps.portal_async_scheduler.core.config import Settings

yaml = YAML(typ="safe")


def load_tasks_config(logger: structlog.stdlib.BoundLogger):
    """加载任务配置文件，包含完整的异常处理"""
    config_dir = Path(__file__).parent.parent / "configs/tasks.yaml"
    try:
        with open(config_dir, "r", encoding="utf-8") as f:
            config = yaml.load(f)

        if not config:
            raise ValueError("tasks.yaml 文件为空或格式错误")

        if "scheduler_tasks" not in config:
            raise ValueError("tasks.yaml 格式错误：缺少 'scheduler_tasks' 键")

        if not isinstance(config["scheduler_tasks"], list):
            raise ValueError("tasks.yaml 格式错误：'scheduler_tasks' 必须是列表类型")

        return config["scheduler_tasks"]
    except FileNotFoundError:
        logger.error(f"任务配置文件不存在: {config_dir}")
        raise
    except ValueError as e:
        logger.error("任务配置文件格式错误", error=str(e))
        raise
    except Exception as e:
        logger.error("加载任务配置失败", exc_info=e)
        raise


# 初始化异步调度器
def initialize_scheduler(logger: structlog.stdlib.BoundLogger, settings: Settings):
    # 配置 executor（异步执行器）
    executors = {
        "default": AsyncIOExecutor()
    }

    # 任务默认配置
    job_defaults = {
        "coalesce": settings.scheduler.job.coalesce,
        "max_instances": settings.scheduler.job.max_instances,
    }

    # 创建异步调度器
    scheduler = AsyncIOScheduler(
        executors=executors,
        job_defaults=job_defaults,
        timezone=settings.scheduler.timezone,
    )

    logger.info("Scheduler initialized successfully")

    return scheduler


# 加载并注册任务到调度器
def register_tasks(logger: structlog.stdlib.BoundLogger, scheduler: AsyncIOScheduler):
    tasks_config = load_tasks_config(logger)

    for task_config in tasks_config:
        if not task_config["enabled"]:
            logger.warning("Task disabled, skip registration", task_name=task_config["name"])
            continue

        # 动态导入任务函数
        try:
            module_path, func_name = task_config["func"].split(":")
            module = importlib.import_module(module_path)
            task_func = getattr(module, func_name)
        except Exception as e:
            logger.error("Failed to import task function", task_name=task_config["name"], exc_info=e)
            continue

        # 添加任务到调度器
        try:
            trigger_type = task_config["trigger"]
            trigger_kwargs = {k: v for k, v in task_config.items() if k not in ["name", "func", "trigger", "enabled"]}

            scheduler.add_job(
                func=task_func,
                trigger=trigger_type,
                id=task_config["name"],
                name=task_config["name"],
                **trigger_kwargs,
            )
            logger.info("Task registered successfully", task_name=task_config["name"], trigger=trigger_type,
                        kwargs=trigger_kwargs)
        except Exception as e:
            logger.error("Failed to register task", task_name=task_config["name"], exc_info=e)
