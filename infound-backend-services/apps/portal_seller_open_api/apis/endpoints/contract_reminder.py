from fastapi import APIRouter, Depends, HTTPException, Query, status

from apps.portal_seller_open_api.core.deps import (
    get_contract_reminder_service,
    get_current_user_info,
)
from apps.portal_seller_open_api.models.contract_reminder import (
    ContractReminderLogListData,
    ContractReminderMonitorListData,
    ContractReminderRuleConfigListData,
    ContractReminderRuleConfigUpdateRequest,
)
from apps.portal_seller_open_api.services.contract_reminder_service import (
    ContractReminderService,
)
from core_base import APIResponse, success_response
from shared_seller_application_services.current_user_info import CurrentUserInfo

router = APIRouter(tags=["样品管理 Contract 提醒"])


@router.get(
    "/sample-monitor/contract-rules",
    response_model=APIResponse[ContractReminderRuleConfigListData],
    response_model_by_alias=True,
    description="获取店铺 contract 提醒规则配置",
)
async def list_contract_reminder_rules(
    shop_id: str = Query(..., alias="shopId", min_length=1),
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
    service: ContractReminderService = Depends(get_contract_reminder_service),
) -> APIResponse[ContractReminderRuleConfigListData]:
    try:
        result = await service.list_rule_configs(current_user_info, shop_id=shop_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)


@router.put(
    "/sample-monitor/contract-rules",
    response_model=APIResponse[ContractReminderRuleConfigListData],
    response_model_by_alias=True,
    description="保存店铺 contract 提醒规则配置",
)
async def save_contract_reminder_rules(
    body: ContractReminderRuleConfigUpdateRequest,
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
    service: ContractReminderService = Depends(get_contract_reminder_service),
) -> APIResponse[ContractReminderRuleConfigListData]:
    try:
        result = await service.save_rule_configs(current_user_info, body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)


@router.get(
    "/sample-monitor/contract-monitors",
    response_model=APIResponse[ContractReminderMonitorListData],
    response_model_by_alias=True,
    description="获取店铺 contract 提醒最新状态列表",
)
async def list_contract_reminder_monitors(
    shop_id: str = Query(..., alias="shopId", min_length=1),
    current_status: str | None = Query(None, alias="currentStatus"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
    service: ContractReminderService = Depends(get_contract_reminder_service),
) -> APIResponse[ContractReminderMonitorListData]:
    try:
        result = await service.list_monitors(
            current_user_info,
            shop_id=shop_id,
            current_status=current_status,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)


@router.get(
    "/sample-monitor/contract-logs",
    response_model=APIResponse[ContractReminderLogListData],
    response_model_by_alias=True,
    description="获取店铺 contract 提醒触发日志",
)
async def list_contract_reminder_logs(
    shop_id: str = Query(..., alias="shopId", min_length=1),
    rule_code: str | None = Query(None, alias="ruleCode"),
    platform_creator_id: str | None = Query(None, alias="platformCreatorId"),
    task_plan_id: str | None = Query(None, alias="taskPlanId"),
    send_status: str | None = Query(None, alias="sendStatus"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
    service: ContractReminderService = Depends(get_contract_reminder_service),
) -> APIResponse[ContractReminderLogListData]:
    try:
        result = await service.list_logs(
            current_user_info,
            shop_id=shop_id,
            rule_code=rule_code,
            platform_creator_id=platform_creator_id,
            task_plan_id=task_plan_id,
            send_status=send_status,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)
