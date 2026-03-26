from fastapi import APIRouter, Depends, HTTPException, status

from apps.portal_inner_open_api.core.deps import (
    get_creator_ingestion_service,
    get_creator_history_service,
)
from apps.portal_inner_open_api.models.creator import (
    CreatorIngestionRequest,
    CreatorIngestionResult,
    CreatorHistoryRequest,
    CreatorHistoryResult,
)
from apps.portal_inner_open_api.services.creator_history_service import (
    CreatorHistoryService,
)
from apps.portal_inner_open_api.services.creator_ingestion_service import (
    CreatorIngestionService,
)
from core_base import APIResponse, success_response

router = APIRouter(prefix="/creators", tags=["Creators"])


@router.post(
    "/ingest",
    response_model=APIResponse[CreatorIngestionResult],
    response_model_by_alias=True,
)
async def ingest_creators(
    payload: CreatorIngestionRequest,
    service: CreatorIngestionService = Depends(get_creator_ingestion_service),
) -> APIResponse[CreatorIngestionResult]:
    try:
        result = await service.ingest(payload)
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
    service: CreatorHistoryService = Depends(get_creator_history_service),
) -> APIResponse[CreatorHistoryResult]:
    try:
        result = await service.fetch(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
