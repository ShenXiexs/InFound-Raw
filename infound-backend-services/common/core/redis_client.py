from typing import Optional

import redis

# Assume these modules are available
from common.core.config import get_settings
from common.core.logger import get_logger

# Fetch settings and logger
settings = get_settings()
logger = get_logger()


class RedisClientManager:
    """
    Redis client manager for initializing the pool and providing client instances.
    """
    # Store pool and client as class attributes
    _pool: Optional[redis.ConnectionPool] = None
    _client: Optional[redis.Redis] = None

    @classmethod
    def initialize(cls) -> None:
        """
        Initialize Redis pool/client and verify connectivity.
        Ensures single initialization.
        """
        if cls._pool is not None:
            # Already initialized.
            return

        try:
            # 1. Create connection pool
            cls._pool = redis.ConnectionPool(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                decode_responses=True,
                encoding="utf-8",
                # Optional parameters such as max_connections
                max_connections=100
            )

            # 2. Create client and test connectivity
            cls._client = redis.Redis(connection_pool=cls._pool)

            # Ping test
            cls._client.ping()

            logger.info(f"Redis pool/client initialized, {settings.REDIS_PREFIX}")
        except Exception as e:
            logger.error(f"Redis initialization failed: {e}", exc_info=True)
            # Reset partially created pool on failure
            cls._pool = None
            cls._client = None
            raise

    @classmethod
    def get_client(cls) -> redis.Redis:
        """
        Return Redis client (backed by the connection pool).
        Initializes lazily on first call.
        """
        if cls._client is None:
            # Lazy init
            cls.initialize()

        # Ensure client initialized
        if cls._client is None:
            raise RuntimeError("Redis client initialization failed.")

        return cls._client


# ----------------------------------------------------
# Public helper (for dependency injection)

def get_redis_client() -> redis.Redis:
    """
    Dependency helper that returns the singleton Redis client.
    """
    return RedisClientManager.get_client()

# Example: initialize on app startup (optional)
# try:
#     RedisClientManager.init_pool()
# except Exception:
#     # Handle exceptions per app needs (e.g., abort startup)
#     pass
