import asyncio
import threading
from contextlib import asynccontextmanager
from typing import Optional, AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    AsyncEngine,
    async_sessionmaker,
)

from core_base import get_logger
from .mysql_setting import MySQLSettings


class DatabaseManager:
    """
    异步数据库连接管理器（单例服务模式）
    """

    _engine: Optional[AsyncEngine] = None
    _session_factory: Optional[async_sessionmaker] = None
    _settings: Optional[MySQLSettings] = None
    _lock = threading.Lock()
    _logger = get_logger("DatabaseManager")

    @classmethod
    def initialize(cls, settings: MySQLSettings) -> None:
        """
        显式初始化：由 ServiceLauncher 在启动阶段调用。
        """
        with cls._lock:
            if cls._engine is not None:
                return

            cls._settings = settings
            try:
                # 1. 创建异步引擎
                cls._engine = create_async_engine(
                    settings.sqlalchemy_database_url,
                    pool_size=getattr(settings, "pool_size", 10),
                    max_overflow=getattr(settings, "max_overflow", 20),
                    pool_recycle=3600,
                    pool_pre_ping=True,
                    echo=False,  # 生产环境建议关闭 SQL 打印，除非调试
                )

                # 2. 使用 async_sessionmaker (SQLAlchemy 2.0+ 推荐)
                cls._session_factory = async_sessionmaker(
                    bind=cls._engine,
                    autoflush=False,
                    expire_on_commit=False,
                )

                cls._logger.info("MySQL 异步连接池初始化成功")
            except Exception as e:
                cls._logger.error(f"MySQL 初始化失败: {e}", exc_info=True)
                cls._engine = None
                cls._session_factory = None
                raise

    @classmethod
    @asynccontextmanager
    async def get_session(cls) -> AsyncGenerator[AsyncSession, None]:
        """
        获取异步会话上下文（无须再传 settings 参数）。
        """
        if cls._session_factory is None:
            # 延迟初始化兜底逻辑
            if cls._settings is None:
                cls._logger.error(
                    "在未调用 initialize 且无配置的情况下尝试获取 Session"
                )
                raise RuntimeError("DatabaseManager must be initialized before use.")
            cls.initialize(cls._settings)

        # 这里的类型检查是为了通过 MyPy 等静态检查
        if cls._session_factory is None:
            raise RuntimeError("DatabaseManager failed to initialize factory.")

        session = cls._session_factory()
        try:
            yield session
            # 兼容仍依赖依赖层自动提交的旧代码；已显式提交的事务不会重复打开连接。
            if session.in_transaction():
                await asyncio.shield(session.commit())
        except Exception as e:
            if session.in_transaction():
                await asyncio.shield(session.rollback())
            cls._logger.error(f"数据库会话异常，已回滚: {e}", exc_info=True)
            raise
        finally:
            await asyncio.shield(session.close())

    @classmethod
    async def close(cls):
        """
        优雅关闭引擎，释放连接池资源。
        """
        with cls._lock:
            if cls._engine:
                cls._logger.info("正在关闭 MySQL 连接池...")
                await cls._engine.dispose()
                cls._engine = None
                cls._session_factory = None
                cls._logger.info("MySQL 连接已释放")
