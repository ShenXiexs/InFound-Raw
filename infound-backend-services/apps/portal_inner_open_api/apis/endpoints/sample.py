from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.database import get_db_session
from common.core.response import APIResponse, success_response
from apps.portal_inner_open_api.models.sample import (
    SampleIngestionRequest,
    SampleIngestionResult,
)
from apps.portal_inner_open_api.services.sample_ingestion_service import (
    sample_ingestion_service,
)

router = APIRouter(prefix="/samples", tags=["Samples"])


@router.post(
    "/ingest",
    response_model=APIResponse[SampleIngestionResult],
    response_model_by_alias=True,
)
async def ingest_samples(
    payload: SampleIngestionRequest,
    session: AsyncSession = Depends(get_db_session),
) -> APIResponse[SampleIngestionResult]:
    try:
        result = await sample_ingestion_service.ingest(payload, session)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
