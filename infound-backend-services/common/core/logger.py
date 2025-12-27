import logging
import os
import sys
from typing import List, Any

import structlog
from structlog.contextvars import merge_contextvars
from structlog.stdlib import ProcessorFormatter

from common.core.config import get_settings, InitializationError

_LOGGING_INITIALIZED = False


def initialize_logging() -> structlog.stdlib.BoundLogger:
    global _LOGGING_INITIALIZED

    if _LOGGING_INITIALIZED:
        return structlog.get_logger()

    try:
        settings = get_settings()
    except InitializationError:
        logging.basicConfig(level=logging.INFO)
        return structlog.get_logger("unknown_app")

    # 1. Create log directory
    os.makedirs(settings.LOG_DIR, exist_ok=True)

    # 2. structlog pre-processors
    shared_processors: List[Any] = [
        merge_contextvars,  # merge contextvars
        # structlog.stdlib.add_logger_name,  # add logger name
        structlog.stdlib.add_log_level,  # add level
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.processors.StackInfoRenderer()
    ]

    # ---------------------------
    # 3. Structured logging: integrate logging <-> structlog
    # ---------------------------
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),  # structlog writes to logging
        wrapper_class=structlog.make_filtering_bound_logger(settings.LOG_LEVEL),
        cache_logger_on_first_use=True,
    )

    # 4. stdlib logger (file backend)
    python_logger = logging.getLogger(settings.APP_NAME)
    python_logger.setLevel(settings.LOG_LEVEL.upper())
    python_logger.handlers.clear()
    python_logger.propagate = False

    # Console: color output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(settings.LOG_LEVEL.upper())
    console_handler.setFormatter(
        ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
            foreign_pre_chain=shared_processors,
        )
    )
    python_logger.addHandler(console_handler)

    # File: JSON-ish output, multi-process safe
    log_file = os.path.join(settings.LOG_DIR, f"{settings.APP_NAME}.log")

    try:
        from concurrent_log_handler import ConcurrentTimedRotatingFileHandler
        FileHandlerImpl = ConcurrentTimedRotatingFileHandler
    except Exception:
        from logging.handlers import TimedRotatingFileHandler
        FileHandlerImpl = TimedRotatingFileHandler

    file_handler = FileHandlerImpl(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=settings.LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"

    file_handler.setLevel(settings.LOG_LEVEL.upper())
    file_handler.setFormatter(
        ProcessorFormatter(
            # File output (machine + human friendly)
            # processor=JSONRenderer(ensure_ascii=False),
            # Console-style output (human friendly)
            processor=structlog.dev.ConsoleRenderer(colors=False),
            foreign_pre_chain=shared_processors,
        )
    )
    python_logger.addHandler(file_handler)

    # Done
    _LOGGING_INITIALIZED = True
    return structlog.get_logger(settings.APP_NAME)


def get_logger(name: str = None):
    global _LOGGING_INITIALIZED

    try:
        settings = get_settings()
    except InitializationError:
        return structlog.get_logger(name or "unknown_app")

    if not _LOGGING_INITIALIZED:
        initialize_logging()

    return structlog.get_logger(name or settings.APP_NAME)
