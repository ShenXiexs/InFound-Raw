from fastapi import APIRouter, Depends, HTTPException, Request, status

from apps.portal_seller_open_api.core.deps import get_sample_monitor_result_service
from apps.portal_seller_open_api.models.entities import CurrentUserInfo
from apps.portal_seller_open_api.models.sample_monitor_result import (
    SampleMonitorResultIngestionRequest,
    SampleMonitorResultIngestionResult,
)
from apps.portal_seller_open_api.services.sample_monitor_result_service import (
    SampleMonitorResultIngestionService,
)
from core_base import APIResponse, success_response

router = APIRouter(
    prefix="/api/v1/rpa/sample-monitor",
    tags=["Seller RPA Sample Monitor"],
)


@router.post(
    "/results",
    response_model=APIResponse[SampleMonitorResultIngestionResult],
    response_model_by_alias=True,
)
async def ingest_sample_monitor_results(
    payload: SampleMonitorResultIngestionRequest,
    request: Request,
    service: SampleMonitorResultIngestionService = Depends(
        get_sample_monitor_result_service
    ),
) -> APIResponse[SampleMonitorResultIngestionResult]:
    current_user: CurrentUserInfo = request.state.current_user_info
    try:
        result = await service.ingest(current_user, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
