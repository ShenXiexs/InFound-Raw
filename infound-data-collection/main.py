import argparse
import asyncio
import signal
import sys
from importlib import import_module
from typing import Optional

import structlog

from common.core.config import initialize_settings, get_settings
from common.core.logger import initialize_logging, get_logger
from common.mq.consumer_base import ConsumerBase

# Global logger placeholder; initialized in main().
logger: Optional[structlog.stdlib.BoundLogger] = None

# Global shutdown signal
shutdown_signal = asyncio.Event()


# 1. Initialize CLI arguments
def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="RabbitMQ Consumer")
    parser.add_argument(
        "--env",
        default="dev",
        choices=["dev", "stg", "pro"],
        help="environment (dev/stg/pro)"
    )
    parser.add_argument(
        "--consumer",
        required=True,
        help="consumer service name"
    )
    return parser.parse_args()


def handle_signals() -> None:
    """Handle OS signals."""
    global logger

    def signal_handler(signum, frame):
        signal_name = signal.Signals(signum).name
        # Signal handler must use the global logger (if initialized).
        if logger:
            logger.info(f"Received signal: {signal_name}, initiating shutdown")
        else:
            # Fallback when logging is not initialized.
            print(f"Received signal: {signal_name}, initiating shutdown (Logger not ready)", file=sys.stderr)

        shutdown_signal.set()

    # Register signal handlers.
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def start_single_consumer(consumer_name: str) -> 'ConsumerBase':
    """Start a single consumer."""
    global logger

    # ConsumerBase lives in common.mq.consumer_base.
    try:
        consumer_module = import_module(f"apps.{consumer_name}.crawler_consumer")
        consumer_class = getattr(consumer_module, "CrawlerConsumer")
        consumer = consumer_class()

        asyncio.create_task(consumer.start())
        logger.info(f"Consumer '{consumer_name}' started successfully.")

        return consumer
    except ImportError:
        logger.critical(
            f"Failed to import consumer module for '{consumer_name}'. Ensure apps/{consumer_name}/crawler_consumer.py and class 'Consumer' exist.")
        raise
    except AttributeError:
        logger.critical(f"Consumer class 'CrawlerConsumer' not found in apps.{consumer_name}.crawler_consumer.")
        raise


async def main() -> None:
    global logger
    args = parse_args()
    consumer = None

    try:
        # A. Initialize settings (must be first).

        initialize_settings(env_arg=args.env, consumer_arg=args.consumer)
        settings = get_settings()

        # B. Initialize logging (after settings).
        initialize_logging()

        # C. Refresh module-level logger (now configured).
        logger = get_logger(__name__)

        # Signal handling (logger ready).
        handle_signals()

        logger.info(
            "Application started",
            consumer_id=settings.CONSUMER,
            env=settings.ENV,
            log_level=settings.LOG_LEVEL
        )

        # Start consumer
        consumer = await start_single_consumer(args.consumer)

        # Wait for shutdown
        logger.info("Application ready, waiting for shutdown signal.")
        await shutdown_signal.wait()
        logger.info("Shutdown signal received, initiating cleanup...")

    except Exception as e:
        # Any startup error is captured and logged.
        if logger:
            logger.critical("Application startup failed", exc_info=e)
        else:
            print(f"FATAL ERROR: Application startup failed: {e}", file=sys.stderr)
        # Ensure non-zero exit
        sys.exit(1)
    finally:
        # Cleanup
        if consumer:
            logger.info("Stopping consumers...")
            await consumer.stop()

        if logger:
            logger.info("All resources cleaned up, application exited.")
        else:
            print("Cleaning up resources and exiting.")


if __name__ == "__main__":
    try:
        # Exceptions outside asyncio.run are handled here.
        asyncio.run(main())
    except Exception:
        # Top-level exception handling is already in main().
        pass
