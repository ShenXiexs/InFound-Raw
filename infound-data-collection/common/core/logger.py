import logging
import os
import sys
from typing import Any, List

import structlog
from structlog.dev import ConsoleRenderer
from structlog.processors import JSONRenderer
from structlog.stdlib import ProcessorFormatter

from common.core.config import InitializationError  # handle uninitialized settings
from common.core.config import get_settings

# Module-level flag indicating logging initialization
_LOGGING_INITIALIZED: bool = False


def initialize_logging() -> structlog.stdlib.BoundLogger:
    """
    Initialize logging once at startup.
    Supports multi-process, multi-level, structured logging.
    """
    global _LOGGING_INITIALIZED

    # Explicit singleton check
    if _LOGGING_INITIALIZED:
        # If already initialized, return configured logger.
        try:
            settings = get_settings()
            return structlog.get_logger(settings.APP_NAME)
        except InitializationError:
            # Fallback (should not happen).
            return structlog.get_logger("unknown_app")

    try:
        # Fetch settings at runtime (ensures initialization).
        settings = get_settings()
    except InitializationError:
        # If settings are missing, use a basic Python logger.
        print("Warning: settings not initialized; using default logging.")
        logging.basicConfig(level=logging.INFO)
        return structlog.get_logger()

    # 1. Create log directory (deferred to initialization).
    os.makedirs(settings.LOG_DIR, exist_ok=True)

    # 2. Define base processor chain (no ExtraAdder/final renderer).
    base_processors: List[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.dev.ConsoleRenderer()
    ]
    # Filter out None
    base_processors = [p for p in base_processors if p is not None]

    # 3. Initialize structlog core config
    structlog.configure(
        processors=base_processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.NOTSET),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False
    )

    # 4. Get or create stdlib logger
    logger = logging.getLogger(settings.APP_NAME)
    logger.setLevel(settings.LOG_LEVEL.upper())
    logger.propagate = False  # avoid duplicate propagation

    # 5. Add handlers (only once).
    # structlog.configure mutates global behavior; rely on _LOGGING_INITIALIZED.

    # -- Console handler (local time, human-friendly) --
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(settings.LOG_LEVEL.upper())
    console_handler.setFormatter(
        ProcessorFormatter(
            # Final renderer: colorized console output
            processor=ConsoleRenderer(colors=sys.stdout.isatty()),
            foreign_pre_chain=base_processors + [structlog.stdlib.ExtraAdder()],
        )
    )
    logger.addHandler(console_handler)

    # -- File handler (concurrent-safe, JSON format) --
    log_file = os.path.join(settings.LOG_DIR, f"{settings.APP_NAME}.log")

    # ⚠️ Multi-process requires ConcurrentRotatingFileHandler
    # Install: pip install concurrent-log-handler
    try:
        from concurrent_log_handler import ConcurrentRotatingFileHandler
        file_handler_class = ConcurrentRotatingFileHandler
    except ImportError:
        # Fallback (not recommended for production)
        import warnings
        warnings.warn(
            "concurrent-log-handler is not installed; log rotation is unsafe in multi-process. "
            "Install: pip install concurrent-log-handler",
            RuntimeWarning
        )
        from logging.handlers import RotatingFileHandler
        file_handler_class = RotatingFileHandler

    file_handler = file_handler_class(
        filename=log_file,
        maxBytes=settings.LOG_FILE_MAX_SIZE * 1024 * 1024,  # uses LOG__FILE_MAX_SIZE
        backupCount=settings.LOG_FILE_BACKUP_COUNT,  # uses LOG__FILE_BACKUP_COUNT
        encoding="utf-8",
    )
    file_handler.setLevel(settings.LOG_LEVEL.upper())
    file_handler.setFormatter(
        ProcessorFormatter(
            # Final renderer: JSON output
            processor=JSONRenderer(),
            foreign_pre_chain=base_processors + [structlog.stdlib.ExtraAdder()],
        )
    )
    logger.addHandler(file_handler)

    # 6. Mark initialized
    _LOGGING_INITIALIZED = True

    # 7. Return bound logger
    return structlog.get_logger(settings.APP_NAME)


# Call at startup (do not auto-run on import)
def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """Return configured structlog logger, auto-initializing if needed."""
    global _LOGGING_INITIALIZED

    try:
        settings = get_settings()
    except InitializationError:
        # Return a temporary logger if settings are missing.
        return structlog.get_logger(name or "unknown_app")

    # Ensure initialized
    if not _LOGGING_INITIALIZED:
        initialize_logging()

    return structlog.get_logger(name or settings.APP_NAME)
