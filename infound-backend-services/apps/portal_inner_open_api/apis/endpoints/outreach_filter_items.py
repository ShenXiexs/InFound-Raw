from fastapi import APIRouter, Depends, HTTPException, status

from apps.portal_inner_open_api.core.deps import (
    get_outreach_filter_items_ingestion_service,
)
from apps.portal_inner_open_api.models.outreach_filter_items import (
    OutreachFilterItemsIngestionRequest,
    OutreachFilterItemsIngestionResult,
)
from apps.portal_inner_open_api.services.outreach_filter_items_ingestion_service import (
    OutreachFilterItemsIngestionService,
)
from core_base import APIResponse, success_response

router = APIRouter(prefix="/outreach_filter_items", tags=["OutreachFilterItems"])


@router.post(
    "/ingest",
    response_model=APIResponse[OutreachFilterItemsIngestionResult],
    response_model_by_alias=True,
)
async def ingest_outreach_filter_items(
    payload: OutreachFilterItemsIngestionRequest,
    service: OutreachFilterItemsIngestionService = Depends(
        get_outreach_filter_items_ingestion_service
    ),
) -> APIResponse[OutreachFilterItemsIngestionResult]:
    try:
        result = await service.ingest(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
