from typing import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.services.creator_detail_result_service import (
    CreatorDetailResultIngestionService,
)
from apps.portal_seller_open_api.services.contract_reminder_service import (
    ContractReminderService,
)
from apps.portal_seller_open_api.services.outreach_result_service import (
    OutreachResultIngestionService,
)
from apps.portal_seller_open_api.services.sample_monitor_result_service import (
    SampleMonitorResultIngestionService,
)
from apps.portal_seller_open_api.services.sms_service import SmsService
from apps.portal_seller_open_api.services.task_runtime_service import (
    SellerRpaTaskRuntimeService,
)
from shared_domain import DatabaseManager
from shared_seller_application_services.current_user_info import CurrentUserInfo
from shared_seller_application_services.token_manager import TokenManager


def get_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise RuntimeError("settings not initialized in app.state")
    return settings


def get_token_manager(request: Request) -> TokenManager:
    token_manager = getattr(request.app.state, "token_manager", None)
    if token_manager is None:
        raise RuntimeError("token_manager not initialized in app.state")
    return token_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with DatabaseManager.get_session() as session:
        yield session


def get_current_user_info(request: Request) -> CurrentUserInfo:
    current_user_info = getattr(request.state, "current_user_info", None)
    if current_user_info is None:
        raise RuntimeError("current_user_info not initialized in app.state")
    return current_user_info


async def get_sms_service(
        settings: Settings = Depends(get_settings),
) -> SmsService:
    return SmsService(settings.sms, settings.redis)


def get_outreach_result_service(
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> OutreachResultIngestionService:
    return OutreachResultIngestionService(db, settings)


def get_creator_detail_result_service(
    db: AsyncSession = Depends(get_db_session),
) -> CreatorDetailResultIngestionService:
    return CreatorDetailResultIngestionService(db)


def get_sample_monitor_result_service(
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> SampleMonitorResultIngestionService:
    return SampleMonitorResultIngestionService(db, settings)


def get_contract_reminder_service(
    db: AsyncSession = Depends(get_db_session),
) -> ContractReminderService:
    return ContractReminderService(db)


def get_task_runtime_service(
    settings: Settings = Depends(get_settings),
) -> SellerRpaTaskRuntimeService:
    return SellerRpaTaskRuntimeService(settings)
