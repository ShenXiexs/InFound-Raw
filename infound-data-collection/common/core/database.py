from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession, create_async_engine, AsyncEngine, AsyncAttrs
)
from sqlalchemy.orm import declarative_base, sessionmaker

from common.core.config import get_settings
from common.core.logger import get_logger

settings = get_settings()
logger = get_logger()

# 基础模型类（集成异步特性）
Base = declarative_base(cls=AsyncAttrs)

# 异步引擎（单例）
engine: Optional[AsyncEngine] = None

# 异步会话工厂（优化配置）
AsyncSessionLocal = sessionmaker(
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    bind=None,  # 延迟绑定引擎
)


def init_database() -> None:
    """初始化 MySQL 连接池（支持动态配置）"""
    global engine
    try:
        # 创建异步引擎（优化连接池配置）
        engine = create_async_engine(
            settings.SQLALCHEMY_DATABASE_URL,
            pool_size=10,  # 核心连接数
            max_overflow=20,  # 最大溢出连接数
            pool_recycle=3600,  # 1小时回收连接（避免 MySQL 8小时超时）
            pool_pre_ping=True,  # 连接前校验（避免无效连接）
            echo=settings.DEBUG,  # 开发环境打印 SQL
            echo_pool=settings.DEBUG,  # 开发环境打印连接池日志
        )
        # 绑定引擎到会话工厂
        AsyncSessionLocal.configure(bind=engine)
        logger.info("MySQL 异步连接池初始化成功", extra={"db_url": settings.SQLALCHEMY_DATABASE_URL})
    except Exception as e:
        logger.error("MySQL 连接池初始化失败", exc_info=True, extra={"error": str(e)})
        raise


@asynccontextmanager
async def get_db() -> AsyncSession:
    """依赖注入：获取 MySQL 异步会话（上下文管理器优化）"""
    global engine
    if not engine:
        init_database()

    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("数据库会话异常", exc_info=True, extra={"error": str(e)})
            raise
        finally:
            await session.close()
