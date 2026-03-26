from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from apps.portal_seller_open_api.core.deps import get_task_runtime_service
from apps.portal_seller_open_api.models.entities import CurrentUserInfo
from apps.portal_seller_open_api.models.task_runtime import (
    SellerRpaTaskClaimResult,
    SellerRpaTaskHeartbeatResult,
    SellerRpaTaskReportRequest,
    SellerRpaTaskReportResult,
    SellerRpaTaskType,
)
from apps.portal_seller_open_api.services.task_runtime_service import (
    SellerRpaTaskRuntimeService,
)
from core_base import APIResponse, success_response

router = APIRouter(prefix="/task", tags=["Seller RPA Task Runtime"])


@router.get(
    "/claim",
    response_model=APIResponse[SellerRpaTaskClaimResult | None],
    response_model_by_alias=False,
)
async def claim_task(
    request: Request,
    task_type: SellerRpaTaskType = Query(...),
    task_id: str | None = Query(None),
    service: SellerRpaTaskRuntimeService = Depends(get_task_runtime_service),
) -> APIResponse[SellerRpaTaskClaimResult | None]:
    current_user: CurrentUserInfo = request.state.current_user_info
    result = await service.claim(current_user, task_type, task_id)
    return success_response(result)


@router.post(
    "/{task_id}/heartbeat",
    response_model=APIResponse[SellerRpaTaskHeartbeatResult],
    response_model_by_alias=False,
)
async def heartbeat_task(
    task_id: str,
    request: Request,
    service: SellerRpaTaskRuntimeService = Depends(get_task_runtime_service),
) -> APIResponse[SellerRpaTaskHeartbeatResult]:
    current_user: CurrentUserInfo = request.state.current_user_info
    try:
        result = await service.heartbeat(current_user, task_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)


@router.post(
    "/{task_id}/report",
    response_model=APIResponse[SellerRpaTaskReportResult],
    response_model_by_alias=False,
)
async def report_task(
    task_id: str,
    payload: SellerRpaTaskReportRequest,
    request: Request,
    service: SellerRpaTaskRuntimeService = Depends(get_task_runtime_service),
) -> APIResponse[SellerRpaTaskReportResult]:
    current_user: CurrentUserInfo = request.state.current_user_info
    try:
        result = await service.report(current_user, task_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
