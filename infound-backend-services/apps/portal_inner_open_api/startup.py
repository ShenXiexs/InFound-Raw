from fastapi import FastAPI

from common.core.database import DatabaseManager
from common.core.logger import get_logger
from common.services.rabbitmq_producer import RabbitMQProducer
from apps.portal_inner_open_api.services.chatbot_schedule_publisher import (
    chatbot_schedule_publisher,
)
from .middlewares.request_filter_middleware import RequestFilterMiddleware

logger = get_logger()


async def startup_hook(app: FastAPI):
    """Service-specific startup logic."""
    logger.info("Running portal_inner_open_api startup hook; initializing DB pool...")
    DatabaseManager.initialize()

    # Initialize RabbitMQ producer
    try:
        await RabbitMQProducer.initialize()
    except Exception as e:
        logger.warning(
            "RabbitMQ initialization failed (chatbot dispatch may be unavailable)",
            error=str(e)
        )

    # Start chatbot schedule publisher (repeat reminders / scheduled sends)
    if getattr(getattr(chatbot_schedule_publisher, "settings", None), "CHATBOT_SCHEDULE_PUBLISHER_ENABLED", True):
        try:
            await chatbot_schedule_publisher.start()
        except Exception as e:
            logger.warning(
                "Chatbot schedule publisher failed to start (reminders may be unavailable)",
                error=str(e),
            )


async def shutdown_hook(app: FastAPI):
    """Service-specific shutdown logic."""
    logger.info("Running portal_inner_open_api shutdown hook...")

    try:
        await chatbot_schedule_publisher.stop()
    except Exception:
        pass
    
    # Close RabbitMQ connection
    try:
        await RabbitMQProducer.close()
    except Exception:
        pass


def register_middlewares(app: FastAPI):
    """
    Register service-specific middleware.

    - Called in create_app() before the app starts.
    - Only registers middleware; does not initialize resources.
    """
    logger.info("Registering portal_inner_open_api middleware")
    # Register token filter middleware
    app.add_middleware(RequestFilterMiddleware)
