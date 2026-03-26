from typing import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.core.token_manager import TokenManager
from apps.portal_seller_open_api.services.creator_detail_result_service import (
    CreatorDetailResultIngestionService,
)
from apps.portal_seller_open_api.services.outreach_result_service import (
    OutreachResultIngestionService,
)
from apps.portal_seller_open_api.services.sample_monitor_result_service import (
    SampleMonitorResultIngestionService,
)
from apps.portal_seller_open_api.services.task_runtime_service import (
    SellerRpaTaskRuntimeService,
)
from shared_domain import DatabaseManager


def get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise RuntimeError("Settings not initialized in app.state")
    return settings


def get_token_manager(request: Request) -> TokenManager:
    token_manager = getattr(request.app.state, "token_manager", None)
    if token_manager is None:
        raise RuntimeError("TokenManager not initialized in app.state")
    return token_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with DatabaseManager.get_session() as session:
        yield session


def get_outreach_result_service(
    db: AsyncSession = Depends(get_db_session),
) -> OutreachResultIngestionService:
    return OutreachResultIngestionService(db)


def get_creator_detail_result_service(
    db: AsyncSession = Depends(get_db_session),
) -> CreatorDetailResultIngestionService:
    return CreatorDetailResultIngestionService(db)


def get_sample_monitor_result_service(
    db: AsyncSession = Depends(get_db_session),
) -> SampleMonitorResultIngestionService:
    return SampleMonitorResultIngestionService(db)


def get_task_runtime_service(
    db: AsyncSession = Depends(get_db_session),
) -> SellerRpaTaskRuntimeService:
    return SellerRpaTaskRuntimeService(db)
