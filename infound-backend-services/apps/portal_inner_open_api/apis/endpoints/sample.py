from fastapi import APIRouter, Depends, HTTPException, status

from apps.portal_inner_open_api.core.deps import (
    get_sample_ingestion_service,
)
from apps.portal_inner_open_api.models.sample import (
    SampleIngestionRequest,
    SampleIngestionResult,
)
from apps.portal_inner_open_api.services import SampleIngestionService
from core_base import APIResponse, success_response

router = APIRouter(prefix="/samples", tags=["Samples"])


@router.post(
    "/ingest",
    response_model=APIResponse[SampleIngestionResult],
    response_model_by_alias=True,
)
async def ingest_samples(
    payload: SampleIngestionRequest,
    service: SampleIngestionService = Depends(get_sample_ingestion_service),
) -> APIResponse[SampleIngestionResult]:
    try:
        result = await service.ingest(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
