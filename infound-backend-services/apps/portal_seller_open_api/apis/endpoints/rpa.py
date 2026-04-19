from fastapi import APIRouter, Depends, HTTPException, Request, status

from apps.portal_seller_open_api.core.deps import get_sample_monitor_result_service, get_creator_detail_result_service, \
    get_outreach_result_service
from apps.portal_seller_open_api.models.creator_detail_result import CreatorDetailResultIngestionResult, \
    CreatorDetailResultIngestionRequest
from apps.portal_seller_open_api.models.entities import CurrentUserInfo
from apps.portal_seller_open_api.models.outreach_result import OutreachResultIngestionResult, \
    OutreachResultIngestionRequest
from apps.portal_seller_open_api.models.sample_monitor_result import (
    SampleMonitorResultIngestionRequest,
    SampleMonitorResultIngestionResult,
)
from apps.portal_seller_open_api.services.creator_detail_result_service import CreatorDetailResultIngestionService
from apps.portal_seller_open_api.services.outreach_result_service import OutreachResultIngestionService
from apps.portal_seller_open_api.services.sample_monitor_result_service import (
    SampleMonitorResultIngestionService,
)
from core_base import APIResponse, success_response

router = APIRouter(
    prefix="/rpa",
    tags=["Seller RPA Result"],
)


@router.post(
    "/outreach/results",
    response_model=APIResponse[OutreachResultIngestionResult],
    response_model_by_alias=True,
)
async def ingest_outreach_results(
        payload: OutreachResultIngestionRequest,
        request: Request,
        service: OutreachResultIngestionService = Depends(get_outreach_result_service),
) -> APIResponse[OutreachResultIngestionResult]:
    current_user: CurrentUserInfo = request.state.current_user_info
    try:
        result = await service.ingest(current_user, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)


@router.post(
    "/creator-details/results",
    response_model=APIResponse[CreatorDetailResultIngestionResult],
    response_model_by_alias=True,
)
async def ingest_creator_detail_results(
        payload: CreatorDetailResultIngestionRequest,
        request: Request,
        service: CreatorDetailResultIngestionService = Depends(
            get_creator_detail_result_service
        ),
) -> APIResponse[CreatorDetailResultIngestionResult]:
    current_user: CurrentUserInfo = request.state.current_user_info
    try:
        result = await service.ingest(current_user, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)


@router.post(
    "/sample-monitor/results",
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
