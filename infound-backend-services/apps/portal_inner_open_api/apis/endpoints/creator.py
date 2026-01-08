from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.database import get_db_session
from common.core.response import APIResponse, success_response
from apps.portal_inner_open_api.models.creator import (
    CreatorIngestionRequest,
    CreatorIngestionResult,
    CreatorHistoryRequest,
    CreatorHistoryResult,
)
from apps.portal_inner_open_api.services.creator_ingestion_service import (
    creator_ingestion_service,
)
from apps.portal_inner_open_api.services.creator_history_service import (
    creator_history_service,
)

router = APIRouter(prefix="/creators", tags=["Creators"])


@router.post(
    "/ingest",
    response_model=APIResponse[CreatorIngestionResult],
    response_model_by_alias=True,
)
async def ingest_creators(
    payload: CreatorIngestionRequest,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[CreatorIngestionResult]:
    try:
        result = await creator_ingestion_service.ingest(payload, session)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)


@router.post(
    "/history",
    response_model=APIResponse[CreatorHistoryResult],
    response_model_by_alias=True,
)
async def fetch_creator_history(
    payload: CreatorHistoryRequest,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[CreatorHistoryResult]:
    try:
        result = await creator_history_service.fetch(payload, session)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
