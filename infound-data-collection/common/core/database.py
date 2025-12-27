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

# Base model (async-friendly)
Base = declarative_base(cls=AsyncAttrs)

# Async engine (singleton)
engine: Optional[AsyncEngine] = None

# Async session factory (tuned defaults)
AsyncSessionLocal = sessionmaker(
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    bind=None,  # bind lazily
)


def init_database() -> None:
    """Initialize the MySQL async connection pool."""
    global engine
    try:
        # Create async engine with tuned pool settings
        engine = create_async_engine(
            settings.SQLALCHEMY_DATABASE_URL,
            pool_size=10,  # base pool size
            max_overflow=20,  # extra connections
            pool_recycle=3600,  # recycle hourly (avoid MySQL 8h timeout)
            pool_pre_ping=True,  # validate before use
            echo=settings.DEBUG,  # log SQL in dev
            echo_pool=settings.DEBUG,  # log pool events in dev
        )
        # Bind engine to session factory
        AsyncSessionLocal.configure(bind=engine)
        logger.info("MySQL async pool initialized", extra={"db_url": settings.SQLALCHEMY_DATABASE_URL})
    except Exception as e:
        logger.error("MySQL pool initialization failed", exc_info=True, extra={"error": str(e)})
        raise


@asynccontextmanager
async def get_db() -> AsyncSession:
    """Dependency helper for a managed async DB session."""
    global engine
    if not engine:
        init_database()

    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("Database session error", exc_info=True, extra={"error": str(e)})
            raise
        finally:
            await session.close()
