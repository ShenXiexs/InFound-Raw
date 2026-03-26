from fastapi import APIRouter, Depends, HTTPException, status

from apps.portal_inner_open_api.core.deps import (
    get_campaign_ingestion_service,
)
from apps.portal_inner_open_api.models.campaign import (
    CampaignIngestionRequest,
    CampaignIngestionResult,
    ProductIngestionRequest,
    ProductIngestionResult,
)
from apps.portal_inner_open_api.services import CampaignIngestionService
from core_base import APIResponse, success_response

router = APIRouter(prefix="", tags=["Campaigns"])


@router.post(
    "/campaigns/ingest",
    response_model=APIResponse[CampaignIngestionResult],
    response_model_by_alias=True,
)
async def ingest_campaigns(
    payload: CampaignIngestionRequest,
    service: CampaignIngestionService = Depends(get_campaign_ingestion_service),
) -> APIResponse[CampaignIngestionResult]:
    try:
        result = await service.ingest_campaigns(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)


@router.post(
    "/products/ingest",
    response_model=APIResponse[ProductIngestionResult],
    response_model_by_alias=True,
)
async def ingest_products(
    payload: ProductIngestionRequest,
    service: CampaignIngestionService = Depends(get_campaign_ingestion_service),
) -> APIResponse[ProductIngestionResult]:
    try:
        result = await service.ingest_products(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
