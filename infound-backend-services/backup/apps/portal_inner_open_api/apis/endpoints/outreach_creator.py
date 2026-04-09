from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.database import get_db_session
from common.core.response import APIResponse, success_response
from apps.portal_inner_open_api.models.outreach_creator import (
    OutreachCreatorIngestionRequest,
    OutreachCreatorIngestionResult,
)
from apps.portal_inner_open_api.services.outreach_creator_ingestion_service import (
    outreach_creator_ingestion_service,
)

router = APIRouter(prefix="/outreach/creators", tags=["Outreach Creators"])


@router.post(
    "/ingest",
    response_model=APIResponse[OutreachCreatorIngestionResult],
    response_model_by_alias=True,
)
async def ingest_outreach_creators(
    payload: OutreachCreatorIngestionRequest,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[OutreachCreatorIngestionResult]:
    """
    建联创作者数据上报接口

    由采集器调用，上报采集到的创作者数据
    """
    try:
        result = await outreach_creator_ingestion_service.ingest(payload, session)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
