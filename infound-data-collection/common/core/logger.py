import logging
import os
import sys
from typing import Any, List

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer
from structlog.stdlib import ProcessorFormatter

from common.core.config import InitializationError  # 导入异常类，以便处理未初始化配置
from common.core.config import get_settings

# 模块级全局状态：显式标记日志系统是否已初始化
_LOGGING_INITIALIZED: bool = False


def initialize_logging() -> structlog.stdlib.BoundLogger:
    """
    初始化日志系统（应用启动时显式调用一次）
    支持多进程、多输出级别、结构化日志
    """
    global _LOGGING_INITIALIZED

    # 显式单例检查
    if _LOGGING_INITIALIZED:
        # 如果已经初始化，直接返回已配置的 Logger
        try:
            settings = get_settings()
            return structlog.get_logger(settings.APP_NAME)
        except InitializationError:
            # 这种情况不应该发生，但作为回退
            return structlog.get_logger("unknown_app")

    try:
        # 运行时获取配置实例，确保配置已被初始化
        settings = get_settings()
    except InitializationError:
        # 如果配置未初始化，至少设置一个基础的 Python Logger
        print("警告：配置尚未初始化，使用默认日志设置。")
        logging.basicConfig(level=logging.INFO)
        return structlog.get_logger()

    # 1. 创建日志目录（延迟到初始化时执行）
    os.makedirs(settings.LOG_DIR, exist_ok=True)  # 使用 LOG__DIR 字段名

    # 2. 定义基础处理器链（不包含 ExtraAdder 和最终渲染器）
    base_processors: List[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.dev.ConsoleRenderer()
    ]
    # 过滤掉 None 值
    base_processors = [p for p in base_processors if p is not None]

    # 3. 初始化 structlog 核心配置
    structlog.configure(
        processors=base_processors,  # DictRenderer 是 structlog 的默认输出格式
        wrapper_class=structlog.make_filtering_bound_logger(logging.NOTSET),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False
    )

    # 4. 获取或创建标准库 Logger
    logger = logging.getLogger(settings.APP_NAME)
    logger.setLevel(settings.LOG_LEVEL.upper())  # 使用 LOG__LEVEL 字段名
    logger.propagate = False  # 防止重复传播到 root logger

    # 5. 添加处理器（仅当不存在时）
    # 由于 structlog.configure 会改变全局行为，因此在 setup_logging 中进行显式初始化更安全，
    # 移除原有的 logger.handlers 检查，转而依赖 _LOGGING_INITIALIZED

    # -- 控制台处理器（本地时间，易读） --
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(settings.LOG_LEVEL.upper())
    console_handler.setFormatter(
        ProcessorFormatter(
            # 最终渲染器：控制台着色输出
            processor=ConsoleRenderer(colors=sys.stdout.isatty()),
            foreign_pre_chain=base_processors + [structlog.stdlib.ExtraAdder()],
        )
    )
    logger.addHandler(console_handler)

    # -- 文件处理器（并发安全，JSON 格式） --
    log_file = os.path.join(settings.LOG_DIR, f"{settings.APP_NAME}.log")

    # ⚠️ 多进程场景必须使用 ConcurrentRotatingFileHandler
    # 安装: pip install concurrent-log-handler
    try:
        from concurrent_log_handler import ConcurrentRotatingFileHandler
        file_handler_class = ConcurrentRotatingFileHandler
    except ImportError:
        # 降级方案：警告并退回标准处理器（不推荐生产用）
        import warnings
        warnings.warn(
            "concurrent-log-handler 未安装，日志轮转在多进程下不安全！"
            "请运行: pip install concurrent-log-handler",
            RuntimeWarning
        )
        from logging.handlers import RotatingFileHandler
        file_handler_class = RotatingFileHandler

    file_handler = file_handler_class(
        filename=log_file,
        maxBytes=settings.LOG_FILE_MAX_SIZE * 1024 * 1024,  # 使用 LOG__FILE_MAX_SIZE 字段名
        backupCount=settings.LOG_FILE_BACKUP_COUNT,  # 使用 LOG__FILE_BACKUP_COUNT 字段名
        encoding="utf-8",
    )
    file_handler.setLevel(settings.LOG_LEVEL.upper())
    file_handler.setFormatter(
        ProcessorFormatter(
            # 最终渲染器：JSON 输出
            processor=JSONRenderer(),
            foreign_pre_chain=base_processors + [structlog.stdlib.ExtraAdder()],
        )
    )
    logger.addHandler(file_handler)

    # 6. 标记已初始化
    _LOGGING_INITIALIZED = True

    # 7. 返回 structlog 的 BoundLogger
    return structlog.get_logger(settings.APP_NAME)


# 应用启动时调用（不要在模块导入时自动执行）
def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """获取已配置好的 structlog logger，自动初始化"""
    global _LOGGING_INITIALIZED

    try:
        settings = get_settings()
    except InitializationError:
        # 如果配置未初始化，返回一个临时的标准 Logger
        return structlog.get_logger(name or "unknown_app")

    # 检查是否已配置
    if not _LOGGING_INITIALIZED:
        initialize_logging()

    return structlog.get_logger(name or settings.APP_NAME)
