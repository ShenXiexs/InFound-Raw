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
    Database connection manager (engine + session factory).
    """
    _engine: Optional[AsyncEngine] = None
    _SessionLocal: Optional[sessionmaker] = None

    @classmethod
    def initialize(cls) -> None:
        """
        Initialize MySQL async engine and session factory.
        """
        if cls._engine:
            return

        try:
            # 1. Create async engine
            cls._engine = create_async_engine(
                settings.SQLALCHEMY_DATABASE_URL,
                pool_size=10,
                max_overflow=20,
                pool_recycle=3600,
                pool_pre_ping=True,
                echo=settings.DEBUG,
                echo_pool=settings.DEBUG,
            )

            # 2. Create and configure session factory
            cls._SessionLocal = sessionmaker(
                class_=AsyncSession,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
                bind=cls._engine,  # bind engine
            )

            logger.info("MySQL async pool initialized")
        except Exception as e:
            logger.error("MySQL pool initialization failed", exc_info=True, extra={"error": str(e)})
            cls._engine = None
            cls._SessionLocal = None
            raise

    @classmethod
    @asynccontextmanager
    async def get_session(cls) -> AsyncGenerator[AsyncSession, None]:
        """
        Dependency helper for a managed async DB session.
        """
        if not cls._SessionLocal:
            # Fallback: initialize if startup hook did not run.
            try:
                cls.initialize()
            except Exception:
                # Ensure the manager is initialized or raise a runtime error
                raise RuntimeError("DatabaseManager is not initialized; call initialize() first.")

        # Create session instance
        async with cls._SessionLocal() as session:
            try:
                # Yield session to business logic
                yield session
                await session.commit()
            except Exception as e:
                # Roll back on errors
                await session.rollback()
                logger.error("Database session error (rolled back)", exc_info=True, extra={"error": str(e)})
                raise
            finally:
                # Ensure session is closed (defensive)
                await session.close()


# ----------------------------------------------------
# External dependency helper (FastAPI Depends)
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency injection hook.
    """
    async with DatabaseManager.get_session() as session:
        yield session
