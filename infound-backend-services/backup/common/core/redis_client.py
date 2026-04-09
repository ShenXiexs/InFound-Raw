from typing import Optional

import redis

# 假设这些模块是可用的
from common.core.config import get_settings
from common.core.logger import get_logger

# 获取配置和日志实例
settings = get_settings()
logger = get_logger()


class RedisClientManager:
    """
    Redis 客户端管理器，用于初始化连接池并提供客户端实例。
    """
    # 使用类属性存储连接池和客户端实例
    _pool: Optional[redis.ConnectionPool] = None
    _client: Optional[redis.Redis] = None

    @classmethod
    def initialize(cls) -> None:
        """
        初始化 Redis 连接池和客户端，并进行连接测试。
        确保只初始化一次。
        """
        if cls._pool is not None:
            # 已经初始化过了，直接返回
            return

        try:
            # 1. 创建连接池
            cls._pool = redis.ConnectionPool(
                host=settings.redis.host,
                port=settings.redis.port,
                password=settings.redis.password,
                db=settings.redis.db,
                decode_responses=True,
                encoding="utf-8",
                # 添加其他可选参数，如 max_connections
                max_connections=100
            )

            # 2. 创建一个基于该连接池的客户端实例，并进行连接测试
            cls._client = redis.Redis(connection_pool=cls._pool)

            # 使用客户端进行 ping 测试
            cls._client.ping()

            logger.info(f"Redis 连接池和客户端初始化成功, {settings.redis.prefix}")
        except Exception as e:
            logger.error(f"Redis 连接初始化失败: {e}", exc_info=True)
            # 初始化失败时，清除可能创建了一半的连接池，并重新抛出异常
            cls._pool = None
            cls._client = None
            raise

    @classmethod
    def get_client(cls) -> redis.Redis:
        """
        获取 Redis 客户端实例（基于连接池）。
        如果是第一次调用，会自动初始化连接池。
        """
        if cls._client is None:
            # 延迟初始化
            cls.initialize()

        # 确保 client 已经初始化成功
        if cls._client is None:
            raise RuntimeError("Redis 客户端初始化失败，无法获取实例。")

        return cls._client


# ----------------------------------------------------
# 模块对外提供的接口 (依赖注入时使用)

def get_redis_client() -> redis.Redis:
    """
    外部依赖注入函数，调用 RedisClientManager 获取单例客户端。
    """
    return RedisClientManager.get_client()

# 示例：在应用启动时提前初始化 (可选)
# try:
#     RedisClientManager.init_pool()
# except Exception:
#     # 根据应用需求处理异常，例如停止应用启动
#     pass
