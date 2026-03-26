from typing import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_creator_open_api.core.config import Settings
from apps.portal_creator_open_api.core.token_manager import TokenManager
from apps.portal_inner_open_api.services import (
    CampaignIngestionService,
    SampleIngestionService,
    ChatbotMessageBuilder,
    CreatorIngestionService,
    CreatorHistoryService,
    OutreachCreatorIngestionService,
    OutreachTaskService,
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


def get_campaign_ingestion_service(
        settings: Settings = Depends(get_settings),
        db: AsyncSession = Depends(get_db_session),
) -> CampaignIngestionService:
    return CampaignIngestionService(settings, db)


def get_sample_ingestion_service(
        settings: Settings = Depends(get_settings),
        db: AsyncSession = Depends(get_db_session),
) -> SampleIngestionService:
    return SampleIngestionService(settings, db)


def get_creator_ingestion_service(
        settings: Settings = Depends(get_settings),
        db: AsyncSession = Depends(get_db_session),
) -> CreatorIngestionService:
    return CreatorIngestionService(settings, db)


def get_creator_history_service(
        db: AsyncSession = Depends(get_db_session),
) -> CreatorHistoryService:
    return CreatorHistoryService(db)


def get_outreach_creator_ingestion_service(
        db: AsyncSession = Depends(get_db_session),
) -> OutreachCreatorIngestionService:
    return OutreachCreatorIngestionService(db)


def get_outreach_task_service(
        db: AsyncSession = Depends(get_db_session),
) -> OutreachTaskService:
    return OutreachTaskService(db)


def get_chatbot_message_builder(
        settings: Settings = Depends(get_settings)
) -> ChatbotMessageBuilder:
    return ChatbotMessageBuilder(settings)
