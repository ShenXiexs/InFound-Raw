from fastapi import FastAPI

from apps.portal_creator_open_api.middlewares.auth_filter_middleware import AuthFilterMiddleware
from common.core.database import DatabaseManager
from common.core.logger import get_logger
from common.core.redis_client import RedisClientManager

# from .middlewares.request_filter_middleware import RequestFilterMiddleware

logger = get_logger()


def startup_hook(app: FastAPI):
    """Service-specific startup logic."""
    logger.info("Running portal_creator_open_api startup hook...")
    RedisClientManager.initialize()
    DatabaseManager.initialize()


def shutdown_hook(app: FastAPI):
    """Service-specific shutdown logic."""
    logger.info("Running portal_creator_open_api shutdown hook...")


def register_middlewares(app: FastAPI):
    """
    Register service-specific middleware.

    - Called in create_app() before the app starts.
    - Only registers middleware; does not initialize resources.
    """
    logger.info("Registering portal_creator_open_api middleware")
    # Register token filter middleware
    app.add_middleware(AuthFilterMiddleware)
