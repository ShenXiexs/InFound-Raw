from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.portal_seller_open_api.core.deps import (
    get_current_user_info,
    get_task_runtime_service,
)
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
from shared_seller_application_services.current_user_info import CurrentUserInfo

router = APIRouter(tags=["任务计划"])


@router.get(
    "/task/claim",
    response_model=APIResponse[SellerRpaTaskClaimResult | None],
    response_model_by_alias=True,
    description="客户端申领任务：支持类型 OUTREACH, CREATOR_DETAIL, SAMPLE_MONITOR, CHAT, URGE_CHAT",
)
async def claim_task(
    task_type: SellerRpaTaskType = Query(...),
    task_id: str | None = Query(None),
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
    service: SellerRpaTaskRuntimeService = Depends(get_task_runtime_service),
) -> APIResponse[SellerRpaTaskClaimResult | None]:
    result = await service.claim(current_user_info, task_type, task_id)
    return success_response(result)


@router.post(
    "/task/{task_id}/heartbeat",
    response_model=APIResponse[SellerRpaTaskHeartbeatResult],
    response_model_by_alias=True,
    description="心跳汇报：更新任务的心跳时间，证明客户端仍在运行",
)
async def heartbeat_task(
    task_id: str,
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
    service: SellerRpaTaskRuntimeService = Depends(get_task_runtime_service),
) -> APIResponse[SellerRpaTaskHeartbeatResult]:
    try:
        result = await service.heartbeat(current_user_info, task_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)


@router.post(
    "/task/{task_id}/report",
    response_model=APIResponse[SellerRpaTaskReportResult],
    response_model_by_alias=True,
    description="结果上报：结束生命周期",
)
async def report_task(
    task_id: str,
    payload: SellerRpaTaskReportRequest,
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
    service: SellerRpaTaskRuntimeService = Depends(get_task_runtime_service),
) -> APIResponse[SellerRpaTaskReportResult]:
    try:
        result = await service.report(current_user_info, task_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
