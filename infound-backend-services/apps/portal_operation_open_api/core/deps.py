from typing import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_operation_open_api.core.config import Settings
from apps.portal_operation_open_api.core.token_manager import TokenManager
from apps.portal_operation_open_api.services.outreach_task_service import OutreachTaskService
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


def get_outreach_task_service(
        db: AsyncSession = Depends(get_db_session),
) -> OutreachTaskService:
    return OutreachTaskService(db)
