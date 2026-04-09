import threading
from typing import Optional

import redis

from core_base import get_logger
from .redis_setting import RedisSettings


class RedisClientManager:
    """
    带日志和线程安全的 Redis 客户端管理器
    """

    # 1. 在类级别定义 Logger，使用类名作为标签
    _logger = get_logger("RedisClientManager")

    _pool: Optional[redis.ConnectionPool] = None
    _client: Optional[redis.Redis] = None
    _settings: Optional[RedisSettings] = None
    _lock = threading.Lock()

    @classmethod
    def initialize(cls, settings: RedisSettings) -> None:
        """显式初始化"""
        with cls._lock:
            if cls._client is not None:
                return
            cls._settings = settings
            cls._setup()

    @classmethod
    def _setup(cls):
        try:
            # 使用类内部的 logger
            cls._logger.info(
                f"正在连接 Redis: {cls._settings.host}:{cls._settings.port}"
            )

            cls._pool = redis.ConnectionPool(
                host=cls._settings.host,
                port=cls._settings.port,
                password=cls._settings.password,
                db=cls._settings.db,
                decode_responses=True,
                max_connections=100,
            )
            cls._client = redis.Redis(connection_pool=cls._pool)
            cls._client.ping()

            cls._logger.info("Redis 初始化成功")
        except Exception as e:
            cls._logger.error(f"Redis 初始化失败: {e}", exc_info=True)
            cls._client = None
            raise

    @classmethod
    def get_client(cls) -> redis.Redis:
        """获取单例，无需传参"""
        if cls._client is None:
            if cls._settings is None:
                cls._logger.error("尝试获取未初始化的 Redis 客户端")
                raise RuntimeError("RedisClientManager 尚未初始化 settings")

            with cls._lock:
                if cls._client is None:
                    cls._setup()
        return cls._client

    @classmethod
    def close(cls):
        if cls._pool:
            cls._pool.disconnect()
            cls._logger.info("Shutting down Redis connections...")
