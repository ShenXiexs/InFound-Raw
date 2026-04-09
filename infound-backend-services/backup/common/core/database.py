from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, AsyncEngine
)
from sqlalchemy.orm import sessionmaker

from common.core.config import get_settings
from common.core.logger import get_logger

settings = get_settings()
logger = get_logger()


class DatabaseManager:
    """
    数据库连接管理器：封装了引擎和会话工厂的创建与配置。
    """
    _engine: Optional[AsyncEngine] = None
    _SessionLocal: Optional[sessionmaker] = None

    @classmethod
    def initialize(cls) -> None:
        """
        初始化 MySQL 异步引擎和会话工厂。
        """
        if cls._engine:
            return

        try:
            # 1. 创建异步引擎
            cls._engine = create_async_engine(
                settings.mysql.sqlalchemy_database_url,
                pool_size=10,
                max_overflow=20,
                pool_recycle=3600,
                pool_pre_ping=True,
                echo=True,
                echo_pool=True,
            )

            # 2. 创建并配置异步会话工厂
            cls._SessionLocal = sessionmaker(
                class_=AsyncSession,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
                bind=cls._engine,  # 直接绑定引擎
            )

            logger.info(f"MySQL 异步连接池初始化成功, 连接串为：{settings.mysql.sqlalchemy_database_url}")

        except Exception as e:
            logger.error("MySQL 连接池初始化失败", exc_info=True, extra={"error": str(e)})
            cls._engine = None
            cls._SessionLocal = None
            raise

    @classmethod
    @asynccontextmanager
    async def get_session(cls) -> AsyncGenerator[AsyncSession, None]:
        """
        依赖注入：获取 MySQL 异步会话（上下文管理器）。
        """
        if not cls._SessionLocal:
            # 兜底：如果生命周期钩子未触发（或被跳过），这里尝试自动初始化一次，避免接口直接 500。
            try:
                cls.initialize()
            except Exception:
                # 确保管理器已经初始化，否则抛出运行时错误
                raise RuntimeError("DatabaseManager 尚未初始化，请先调用 initialize() 方法。")

        # 从会话工厂创建会话实例
        async with cls._SessionLocal() as session:
            try:
                # 注入 session 到业务逻辑
                yield session
                await session.commit()
            except Exception as e:
                # 出现异常时，进行回滚
                await session.rollback()
                logger.error("数据库会话异常（已回滚）", exc_info=True, extra={"error": str(e)})
                raise
            finally:
                # 无论如何，确保会话被关闭
                # 注意：SessionLocal() 已经实现了 __aexit__，这里显式 close 更多是防御性编程
                await session.close()


# ----------------------------------------------------
# 外部依赖注入函数（用于 FastAPI Depends）
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 依赖注入点。
    """
    async with DatabaseManager.get_session() as session:
        yield session
