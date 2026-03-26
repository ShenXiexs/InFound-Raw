from fastapi import APIRouter, Depends, HTTPException, status

from apps.portal_inner_open_api.core.deps import (
    get_outreach_creator_ingestion_service,
)
from apps.portal_inner_open_api.models.outreach_creator import (
    OutreachCreatorIngestionRequest,
    OutreachCreatorIngestionResult,
)
from apps.portal_inner_open_api.services.outreach_creator_ingestion_service import (
    OutreachCreatorIngestionService,
)
from core_base import APIResponse, success_response

router = APIRouter(prefix="/outreach/creators", tags=["Outreach Creators"])


@router.post(
    "/ingest",
    response_model=APIResponse[OutreachCreatorIngestionResult],
    response_model_by_alias=True,
)
async def ingest_outreach_creators(
        payload: OutreachCreatorIngestionRequest,
        service: OutreachCreatorIngestionService = Depends(
            get_outreach_creator_ingestion_service
        ),
) -> APIResponse[OutreachCreatorIngestionResult]:
    """
    建联创作者数据上报接口

    由采集器调用，上报采集到的创作者数据
    """
    try:
        result = await service.ingest(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
