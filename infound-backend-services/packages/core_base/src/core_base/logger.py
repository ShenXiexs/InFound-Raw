import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from typing import List, Any

import structlog
from concurrent_log_handler import ConcurrentTimedRotatingFileHandler
from structlog.contextvars import merge_contextvars
from structlog.stdlib import ProcessorFormatter

from core_base.settings import LogSettings

_LOGGING_INITIALIZED = False


def initialize_logging(settings: LogSettings) -> structlog.stdlib.BoundLogger:
    global _LOGGING_INITIALIZED

    if _LOGGING_INITIALIZED:
        return structlog.get_logger()

    # 1. 创建日志目录
    os.makedirs(settings.dir, exist_ok=True)

    # 2. 定义共享的处理器链（转换数据格式）
    shared_processors: List[Any] = [
        merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # ---------------------------
    # 3. 结构化处理：整合 logging ↔ structlog
    # ---------------------------
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),  # ⭐ 核心：structlog 写入 logging
        wrapper_class=structlog.make_filtering_bound_logger(settings.level),
        cache_logger_on_first_use=True,
    )

    # 4. 配置 Root Logger (关键点：接管全局日志)
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.level.upper())

    # 清除残留的 Handler (如 uvicorn 默认带的)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 控制台：彩色输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(settings.level.upper())
    console_handler.setFormatter(
        ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
            foreign_pre_chain=shared_processors,
        )
    )
    root_logger.addHandler(console_handler)

    # 文件：JSON 日志，多进程安全
    log_file = os.path.join(settings.dir, f"{settings.app_name}.log")

    try:
        file_handler = ConcurrentTimedRotatingFileHandler(
            filename=log_file,
            when="midnight",
            interval=1,
            backupCount=settings.file_backup_count,
            encoding="utf-8",
        )
    except ImportError:
        file_handler = TimedRotatingFileHandler(
            filename=log_file,
            when="midnight",
            backupCount=settings.file_backup_count,
            encoding="utf-8",
        )

    file_handler.setFormatter(
        ProcessorFormatter(
            # 文件输出也使用 ConsoleRenderer (如果你想要机器友好的 JSON，可换成 JSONRenderer)
            processor=structlog.dev.ConsoleRenderer(colors=False),
            foreign_pre_chain=shared_processors,
        )
    )
    root_logger.addHandler(file_handler)

    # 5. 特殊处理：接管 Uvicorn 等第三方库日志
    # 将它们的日志全部向上抛给 root_logger 处理
    for name in ["uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"]:
        l = logging.getLogger(name)
        l.handlers = []
        l.propagate = True

    # 完成
    _LOGGING_INITIALIZED = True
    return structlog.get_logger()


def get_logger(name: str = None, settings: LogSettings = None) -> structlog.stdlib.BoundLogger:
    global _LOGGING_INITIALIZED

    # 1. 确保在获取任何 logger 之前已经初始化配置
    if not _LOGGING_INITIALIZED:
        # 如果调用者没传 settings，则尝试实例化一个默认的
        if settings is None:
            try:
                settings = LogSettings()
            except Exception:
                # 最后的防线：如果 LogSettings 实例化失败（如缺少环境变量），
                # 这里建议抛出更清晰的错误，或者打印到终端
                print("Warning: LogSettings not provided and default creation failed.")
                return structlog.get_logger(name)

        initialize_logging(settings)

    # 2. 返回绑定的 logger
    # 如果 name 为 None，structlog 会返回当前上下文相关的 logger
    return structlog.get_logger(name)
