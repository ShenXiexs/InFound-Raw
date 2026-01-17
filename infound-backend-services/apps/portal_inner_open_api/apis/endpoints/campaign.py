from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.database import get_db_session
from common.core.response import APIResponse, success_response
from apps.portal_inner_open_api.models.campaign import (
    CampaignIngestionRequest,
    CampaignIngestionResult,
    ProductIngestionRequest,
    ProductIngestionResult,
)
from apps.portal_inner_open_api.services.campaign_ingestion_service import (
    campaign_ingestion_service,
)

router = APIRouter(prefix="", tags=["Campaigns"])


@router.post(
    "/campaigns/ingest",
    response_model=APIResponse[CampaignIngestionResult],
    response_model_by_alias=True,
)
async def ingest_campaigns(
    payload: CampaignIngestionRequest,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[CampaignIngestionResult]:
    try:
        result = await campaign_ingestion_service.ingest_campaigns(payload, session)
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
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[ProductIngestionResult]:
    try:
        result = await campaign_ingestion_service.ingest_products(payload, session)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
