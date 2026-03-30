from typing import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_web_socket.core.config import Settings
from shared_domain import DatabaseManager
from shared_seller_application_services.token_manager import TokenManager


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
