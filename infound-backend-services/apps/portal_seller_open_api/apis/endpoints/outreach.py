import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.core.deps import (
    get_current_user_info,
    get_db_session,
    get_outreach_result_service,
    get_settings,
)
from apps.portal_seller_open_api.models.dtos.outreach import (
    CreateOutreachTaskRequest,
    CreateOutreachTaskData,
    OutreachTaskDetailResponse,
    UpdateOutreachTaskRequest,
    UpdateOutreachTaskData,
    StartOutreachTaskRequest,
    StartOutreachTaskData,
    EndOutreachTaskRequest,
    EndOutreachTaskData,
    CreatorFilterDTO,
    OutreachTaskListRequest,
    OutreachTaskListData,
    OutreachTaskListItem,
)
from apps.portal_seller_open_api.models.outreach_result import (
    OutreachResultIngestionRequest,
    OutreachResultIngestionResult,
)
from apps.portal_seller_open_api.services.outreach_result_service import (
    OutreachResultIngestionService,
)
from apps.portal_seller_open_api.services.normalization import clean_text
from apps.portal_seller_open_api.services.rpa_script_service import (
    SellerRpaScriptService,
)
from apps.portal_seller_open_api.services.task_dispatch_service import (
    SellerRpaTaskDispatchService,
)
from apps.portal_seller_open_api.services.task_notification_service import (
    SellerRpaTaskNotificationService,
)
from apps.portal_seller_open_api.services.task_slot_dispatch_service import (
    SellerRpaTaskSingleSlotDispatchService,
)
from core_base import APIResponse, error_response, get_logger, success_response
from shared_seller_application_services.current_user_info import CurrentUserInfo
from shared_domain import DatabaseManager
from shared_domain.models.task_plan_extension import TaskStatus
from shared_domain.models.infound import (
    IfIdentityUsers,
    SellerTkRpaTaskPlans,
    SellerTkOutreachSettings,
    SellerTkShopPlatformSettings,
    SellerTkShops,
)

router = APIRouter(tags=["建联"])
logger = get_logger(__name__)


@router.post(
    "/api/v1/rpa/outreach/results",
    response_model=APIResponse[OutreachResultIngestionResult],
    response_model_by_alias=True,
)
async def ingest_outreach_results(
    payload: OutreachResultIngestionRequest,
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
    service: OutreachResultIngestionService = Depends(get_outreach_result_service),
) -> APIResponse[OutreachResultIngestionResult]:
    try:
        result = await service.ingest(current_user_info, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return success_response(result)


def _to_bit(value: bool) -> int:
    return 1 if value else 0


def _strategy_from_mode(mode: str) -> int:
    mapping = {
        "ALL": 0,
        "NEW_ONLY": 1,
        "NEW_AND_UNREPLIED": 2,
    }
    return mapping[mode]


def _mode_from_strategy(strategy: int | None) -> str:
    mapping = {
        0: "ALL",
        1: "NEW_ONLY",
        2: "NEW_AND_UNREPLIED",
    }
    return mapping.get(strategy, "ALL")


def _status_to_text(status_value) -> str:
    text = str(status_value or "").strip().upper()
    mapping = {
        "0": TaskStatus.PENDING.value,
        TaskStatus.PENDING.value: TaskStatus.PENDING.value,
        "1": TaskStatus.RUNNING.value,
        TaskStatus.RUNNING.value: TaskStatus.RUNNING.value,
        "2": TaskStatus.CANCELLED.value,
        TaskStatus.CANCELLED.value: TaskStatus.CANCELLED.value,
        "3": TaskStatus.COMPLETED.value,
        TaskStatus.COMPLETED.value: TaskStatus.COMPLETED.value,
    }
    return mapping.get(text, text or TaskStatus.PENDING.value)


def _parse_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return int(value) != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "no", "n", "off"}:
            return False
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
    return bool(value)


def _parse_message_ext(raw: str | None) -> tuple[bool, list[str]]:
    if not raw:
        return False, []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return False, []
    attach_products = _parse_bool(data.get("attachProducts"))
    product_ids = data.get("productIds") or []
    if not isinstance(product_ids, list):
        product_ids = []
    product_ids = [str(item).strip() for item in product_ids if str(item).strip()]
    return attach_products, product_ids


def _start_time_from_epoch(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _to_millis_precision(value: datetime) -> datetime:
    utc_value = _to_utc(value)
    return utc_value.replace(microsecond=(utc_value.microsecond // 1000) * 1000)


def _bit_to_bool(value) -> bool:
    if value in (None, 0, False):
        return False
    if value in (1, True):
        return True
    if isinstance(value, (bytes, bytearray)):
        if len(value) == 0:
            return False
        return int.from_bytes(value, byteorder="big", signed=False) != 0
    return bool(value)


def _status_tokens(status: str) -> set[str]:
    normalized = status.strip().upper()
    mapping = {
        TaskStatus.PENDING.value: {TaskStatus.PENDING.value, "0"},
        TaskStatus.RUNNING.value: {TaskStatus.RUNNING.value, "1"},
        TaskStatus.CANCELLED.value: {TaskStatus.CANCELLED.value, "2"},
        TaskStatus.COMPLETED.value: {TaskStatus.COMPLETED.value, "3"},
        "0": {TaskStatus.PENDING.value, "0"},
        "1": {TaskStatus.RUNNING.value, "1"},
        "2": {TaskStatus.CANCELLED.value, "2"},
        "3": {TaskStatus.COMPLETED.value, "3"},
    }
    return mapping.get(normalized, set())


def _running_status_tokens() -> set[str]:
    return {TaskStatus.RUNNING.value, "1"}


async def _upsert_outreach_rpa_plan(
    db: AsyncSession,
    *,
    task_id: str,
    user_id: str,
    task_payload: dict,
    scheduled_time: datetime,
    now: datetime,
) -> None:
    plan_stmt = select(SellerTkRpaTaskPlans).where(SellerTkRpaTaskPlans.id == task_id).with_for_update()
    plan_row = (await db.execute(plan_stmt)).scalar_one_or_none()
    if plan_row is None:
        db.add(
            SellerTkRpaTaskPlans(
                id=task_id,
                user_id=user_id,
                task_type="OUTREACH",
                task_payload=task_payload,
                status=TaskStatus.PENDING.value,
                scheduled_time=scheduled_time,
                start_time=None,
                end_time=None,
                heartbeat_at=None,
                error_msg=None,
                creator_id=user_id,
                creation_time=now,
                last_modifier_id=user_id,
                last_modification_time=now,
            )
        )
    else:
        plan_row.user_id = user_id
        plan_row.task_type = "OUTREACH"
        plan_row.task_payload = task_payload
        plan_row.status = TaskStatus.PENDING.value
        plan_row.scheduled_time = scheduled_time
        plan_row.start_time = None
        plan_row.end_time = None
        plan_row.heartbeat_at = None
        plan_row.error_msg = None
        plan_row.last_modifier_id = user_id
        plan_row.last_modification_time = now

def _uppercase_uuid() -> str:
    return str(uuid.uuid4()).upper()


def _map_avg_commission_rate(value: int | None) -> str:
    mapping = {
        20: "Less than 20%",
        15: "Less than 15%",
        10: "Less than 10%",
        5: "Less than 5%",
    }
    return mapping.get(value, "All")


def _map_content_type(value: int | None) -> str:
    mapping = {
        1: "Video",
        2: "LIVE",
    }
    return mapping.get(value, "All")


def _map_creator_agency(value: int | None) -> str:
    mapping = {
        1: "Managed by Agency",
        2: "Independent creators",
    }
    return mapping.get(value, "All")


def _map_follower_gender(value: int | None) -> str:
    mapping = {
        1: "Female",
        2: "Male",
    }
    return mapping.get(value, "All")


def _map_est_post_rate(value: int | None) -> str:
    mapping = {
        1: "OK",
        2: "Good",
        3: "Better",
    }
    return mapping.get(value, "All")


def _build_outreach_filter_payload(task: SellerTkOutreachSettings) -> dict:
    fans_count_range = task.filter_fans_count_range or {}
    return {
        "creatorFilters": {
            "productCategorySelections": task.filter_product_categories or [],
            "avgCommissionRate": _map_avg_commission_rate(task.filter_avg_commission_rate),
            "contentType": _map_content_type(task.filter_content_types),
            "creatorAgency": _map_creator_agency(task.filter_creator_agency),
            "spotlightCreator": False,
            "fastGrowing": _bit_to_bool(task.filter_fast_growth_list),
            "notInvitedInPast90Days": _bit_to_bool(task.filter_uninvited_creators_in_90_days),
        },
        "followerFilters": {
            "followerAgeSelections": task.filter_fans_age_range or [],
            "followerGender": _map_follower_gender(task.filter_fans_gender),
            "followerCountMin": str(fans_count_range.get("min") or ""),
            "followerCountMax": str(fans_count_range.get("max") or ""),
        },
        "performanceFilters": {
            "gmvSelections": task.filter_gmv_range or [],
            "itemsSoldSelections": task.filter_sales_count_range or [],
            "averageViewsPerVideoMin": str(task.filter_min_avg_video_views or ""),
            "averageViewsPerVideoShoppableVideosOnly": False,
            "averageViewersPerLiveMin": str(task.filter_min_avg_live_views or ""),
            "averageViewersPerLiveShoppableLiveOnly": False,
            "engagementRateMinPercent": str(task.filter_min_engagement_rate or ""),
            "engagementRateShoppableVideosOnly": False,
            "estPostRate": _map_est_post_rate(task.filter_creator_estimated_publish_rate),
            "brandCollaborationSelections": task.filter_co_branding or [],
        },
        "searchKeyword": (task.search_keywords or "").strip(),
    }


async def _load_outreach_filter_script(
    db: AsyncSession,
    *,
    region_code: str,
    shop_type: str,
) -> dict | None:
    stmt = select(SellerTkShopPlatformSettings).where(
        SellerTkShopPlatformSettings.region_code == region_code,
        SellerTkShopPlatformSettings.shop_type == shop_type,
        SellerTkShopPlatformSettings.is_active == 1,
    ).limit(1)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    if isinstance(row.creator_filter_items, dict):
        return row.creator_filter_items
    return None


async def _register_outreach_filter_script(
    db: AsyncSession,
    *,
    actor_id: str,
    region_code: str,
    shop_type: str,
    filter_script: dict | None,
) -> tuple[str | None, str | None]:
    if not isinstance(filter_script, dict) or not filter_script:
        return None, None

    normalized_region = str(region_code or "").strip().upper()
    normalized_shop_type = str(shop_type or "").strip().upper()
    if not normalized_region or not normalized_shop_type:
        return None, None

    generated_at = clean_text(filter_script.get("generated_at"))
    script_service = SellerRpaScriptService(db)
    return await script_service.upsert_script_snapshot(
        actor_id=actor_id,
        code=f"OUTREACH_FILTER_{normalized_region}_{normalized_shop_type}",
        name=f"建联筛选脚本-{normalized_region}-{normalized_shop_type}",
        script=filter_script,
        version_hint=generated_at,
    )


def _build_outreach_setting_snapshot(
    *,
    user_id: str,
    task: SellerTkOutreachSettings,
    shop: SellerTkShops,
    task_status: str,
    scheduled_time: datetime,
    attach_products: bool,
    product_ids: list[str],
    filter_script_code: str | None,
    filter_script_version: str | None,
) -> dict:
    filter_payload = _build_outreach_filter_payload(task)
    return {
        "id": task.id,
        "userId": str(user_id or "").strip(),
        "shopId": shop.id,
        "shopRegionCode": str(shop.shop_region_code or "").strip().upper(),
        "taskName": task.task_name,
        "duplicateCheckType": task.duplicate_check_type,
        "duplicateCheckCode": task.duplicate_check_code,
        "messageSendStrategy": task.message_send_strategy,
        "outreachMode": _mode_from_strategy(task.message_send_strategy),
        "taskType": str(task.task_type or "OUTREACH").strip().upper() or "OUTREACH",
        "status": _status_to_text(task.status),
        "taskStatus": task_status,
        "message": task.message,
        "messageExtRaw": task.message,
        "searchKeywords": (task.search_keywords or "").strip() or None,
        "filterProductCategories": task.filter_product_categories or [],
        "filterAvgCommissionRate": task.filter_avg_commission_rate,
        "filterContentTypes": task.filter_content_types,
        "filterCreatorAgency": task.filter_creator_agency,
        "filterFastGrowthList": _bit_to_bool(task.filter_fast_growth_list),
        "filterUninvitedCreatorsIn90Days": _bit_to_bool(task.filter_uninvited_creators_in_90_days),
        "filterFansAgeRange": task.filter_fans_age_range or [],
        "filterFansGender": task.filter_fans_gender,
        "filterFansCountRange": task.filter_fans_count_range or {},
        "filterGmvRange": task.filter_gmv_range or [],
        "filterSalesCountRange": task.filter_sales_count_range or [],
        "filterMinAvgVideoViews": task.filter_min_avg_video_views,
        "filterMinAvgLiveViews": task.filter_min_avg_live_views,
        "filterMinEngagementRate": task.filter_min_engagement_rate,
        "filterCreatorEstimatedPublishRate": task.filter_creator_estimated_publish_rate,
        "filterCoBranding": task.filter_co_branding or [],
        "filterSortBy": task.filter_sort_by,
        "firstMessage": task.first_message,
        "secondMessage": task.second_message,
        "planExecuteTime": task.plan_execute_time,
        "expectCount": task.expect_count,
        "attachProducts": attach_products,
        "productIds": product_ids,
        "filterScriptCode": filter_script_code,
        "filterScriptVersion": filter_script_version,
        "creatorFilters": filter_payload["creatorFilters"],
        "followerFilters": filter_payload["followerFilters"],
        "performanceFilters": filter_payload["performanceFilters"],
        "searchKeyword": filter_payload["searchKeyword"],
        "creatorId": task.creator_id,
        "creationTime": task.creation_time.isoformat() if task.creation_time else None,
        "lastModifierId": task.last_modifier_id,
        "lastModificationTime": task.last_modification_time.isoformat() if task.last_modification_time else None,
        "scheduledTime": scheduled_time.isoformat(),
    }


def _build_outreach_task_payload(
    *,
    user_id: str,
    task: SellerTkOutreachSettings,
    shop: SellerTkShops,
    scheduled_time: datetime,
    task_status: str,
    filter_script: dict | None,
    filter_script_code: str | None,
    filter_script_version: str | None,
) -> dict:
    attach_products, product_ids = _parse_message_ext(task.message)
    filter_payload = _build_outreach_filter_payload(task)
    platform_shop_id = str(shop.platform_shop_code or "").strip()
    session_node = {
        "region": str(shop.shop_region_code or "").strip().upper(),
        "headless": False,
    }
    if platform_shop_id:
        session_node["loginStatePath"] = (
            f"%userData%/tk/{str(user_id or '').strip()}/{shop.id}/{platform_shop_id}.json"
        )
    setting_snapshot = _build_outreach_setting_snapshot(
        user_id=user_id,
        task=task,
        shop=shop,
        task_status=task_status,
        scheduled_time=scheduled_time,
        attach_products=attach_products,
        product_ids=product_ids,
        filter_script_code=filter_script_code,
        filter_script_version=filter_script_version,
    )
    payload_node = {
        "taskId": task.id,
        "userId": str(user_id or "").strip(),
        "taskType": "OUTREACH",
        "taskStatus": task_status,
        "taskName": task.task_name,
        "shopId": shop.id,
        "shopRegionCode": str(shop.shop_region_code or "").strip().upper(),
        "searchKeyword": filter_payload["searchKeyword"],
        "searchKeywords": filter_payload["searchKeyword"],
        "duplicateCheckType": task.duplicate_check_type,
        "duplicateCheckCode": task.duplicate_check_code,
        "messageSendStrategy": task.message_send_strategy,
        "outreachMode": _mode_from_strategy(task.message_send_strategy),
        "message": task.first_message,
        "firstMessage": task.first_message,
        "secondMessage": task.second_message,
        "expectCount": task.expect_count,
        "attachProducts": attach_products,
        "productIds": product_ids,
        "filterSortBy": int(task.filter_sort_by) + 1 if task.filter_sort_by is not None else None,
        "planExecuteTime": int(scheduled_time.timestamp()),
        "messageExtRaw": task.message,
        "filterScriptCode": filter_script_code,
        "filterScriptVersion": filter_script_version,
        "outreachSetting": setting_snapshot,
        **filter_payload,
    }
    if filter_script:
        payload_node["filterScript"] = filter_script

    return {
        "task": {
            "taskId": task.id,
            "taskType": "OUTREACH",
            "taskName": task.task_name,
            "taskStatus": task_status,
            "userId": str(user_id or "").strip(),
            "shopId": shop.id,
            "shopRegionCode": str(shop.shop_region_code or "").strip().upper(),
            "scheduledTime": scheduled_time.isoformat(),
            "creatorId": task.creator_id,
            "creationTime": task.creation_time.isoformat() if task.creation_time else None,
            "lastModifierId": task.last_modifier_id,
            "lastModificationTime": task.last_modification_time.isoformat() if task.last_modification_time else None,
        },
        "input": {
            "session": session_node,
            "payload": payload_node,
        },
        "executor": {
            "host": "frontend.desktop",
            "dispatchMode": "user_notification",
            "transport": "rabbitmq_web_stomp",
            "authMode": "jwt",
        },
    }


def _build_transient_outreach_task_plan(
    *,
    task_id: str,
    user_id: str,
    task_payload: dict,
    scheduled_time: datetime,
    now: datetime,
) -> SellerTkRpaTaskPlans:
    return SellerTkRpaTaskPlans(
        id=task_id,
        user_id=user_id,
        task_type="OUTREACH",
        task_payload=task_payload,
        status=TaskStatus.PENDING.value,
        scheduled_time=scheduled_time,
        start_time=None,
        end_time=None,
        heartbeat_at=None,
        error_msg=None,
        creator_id=user_id,
        creation_time=now,
        last_modifier_id=user_id,
        last_modification_time=now,
    )


async def _dispatch_or_schedule_outreach_task_plan(
    *,
    settings,
    task_id: str,
    user_id: str,
    task_payload: dict,
    scheduled_time: datetime,
    now: datetime,
    dispatch_immediately: bool,
    dispatch_failure_message: str,
    schedule_failure_message: str,
    fallback_schedule_failure_message: str | None = None,
) -> bool:
    try:
        transient_task_plan = _build_transient_outreach_task_plan(
            task_id=task_id,
            user_id=user_id,
            task_payload=task_payload,
            scheduled_time=scheduled_time,
            now=now,
        )
    except Exception as exc:
        logger.error(
            "构建临时建联任务计划失败",
            exc_info=exc,
            task_id=task_id,
            user_id=user_id,
        )
        return False

    dispatch_service = SellerRpaTaskDispatchService(settings)
    if dispatch_immediately:
        try:
            async with DatabaseManager.get_session() as dispatch_db:
                slot_dispatch_service = SellerRpaTaskSingleSlotDispatchService(
                    dispatch_db, settings
                )
                await slot_dispatch_service.dispatch_if_slot_available(
                    transient_task_plan,
                    payload={},
                )
            return True
        except Exception as exc:
            logger.error(
                dispatch_failure_message,
                exc_info=exc,
                task_id=task_id,
                user_id=user_id,
            )
            if not fallback_schedule_failure_message:
                return False
            try:
                await dispatch_service.schedule_task_plan(transient_task_plan)
                return False
            except Exception:
                logger.error(
                    fallback_schedule_failure_message,
                    exc_info=True,
                    task_id=task_id,
                    user_id=user_id,
                )
                return False

    try:
        await dispatch_service.schedule_task_plan(transient_task_plan)
        return True
    except Exception as exc:
        logger.error(
            schedule_failure_message,
            exc_info=exc,
            task_id=task_id,
            user_id=user_id,
        )
        return False


@router.post(
    "/outreach/task-settings",
    response_model=APIResponse[OutreachTaskListData],
    response_model_by_alias=True,
    description="获取配置列表",
)
@router.get(
    "/outreach/settings",
    response_model=APIResponse[OutreachTaskListData],
    response_model_by_alias=True,
    description="获取配置列表（兼容旧入口）",
)
async def list_outreach_tasks(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
    body: OutreachTaskListRequest = Body(..., description="任务列表筛选条件"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100, description="每页数量"),
) -> APIResponse[OutreachTaskListData]:
    user_id = current_user_info.user_id
    shop_id = body.shopId
    keyword = body.keyword
    status = body.status

    # 校验店铺归属
    shop_stmt = select(SellerTkShops.id).where(
        and_(
            SellerTkShops.id == shop_id,
            SellerTkShops.user_id == user_id,
            SellerTkShops.deleted == 0,
        )
    )
    owned_shop = (await db.execute(shop_stmt)).scalar_one_or_none()
    if not owned_shop:
        return error_response(message="店铺不存在或无权限访问", code=403)

    stmt = select(SellerTkOutreachSettings).where(
        and_(
            SellerTkOutreachSettings.user_id == user_id,
            SellerTkOutreachSettings.shop_id == shop_id,
        )
    )

    if keyword:
        normalized = keyword.strip()
        if normalized:
            stmt = stmt.where(SellerTkOutreachSettings.task_name.ilike(f"%{normalized}%"))

    if status:
        tokens = _status_tokens(status)
        if not tokens:
            return error_response(message="status 参数非法", code=400)
        stmt = stmt.where(func.upper(SellerTkOutreachSettings.status).in_(tokens))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int((await db.execute(count_stmt)).scalar() or 0)

    offset = (page - 1) * page_size
    stmt = (
        stmt
        .order_by(SellerTkOutreachSettings.last_modification_time.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()

    items = [
        OutreachTaskListItem(
            taskId=row.id,
            taskName=row.task_name,
            startTime=_start_time_from_epoch(row.plan_execute_time),
            plannedCount=row.expect_count or 0,
            realCount=row.real_count or 0,
            newCount=row.new_count or 0,
            spendTime=row.spend_time or 0,
            status=_status_to_text(row.status),
            lastModificationTime=_to_utc(row.last_modification_time),
        )
        for row in rows
    ]

    return success_response(
        data=OutreachTaskListData(
            total=total,
            page=page,
            pageSize=page_size,
            items=items,
        )
    )


@router.post(
    "/outreach/settings",
    response_model=APIResponse[CreateOutreachTaskData],
    response_model_by_alias=True,
    description="新建建联任务",
)
async def create_outreach_task(
    request: Request,
    body: CreateOutreachTaskRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
) -> APIResponse[CreateOutreachTaskData]:
    user_id = current_user_info.user_id
    now = _to_millis_precision(datetime.now(timezone.utc))
    user_stmt = select(IfIdentityUsers).where(
        and_(
            IfIdentityUsers.id == user_id,
            (IfIdentityUsers.deleted.is_(None)) | (IfIdentityUsers.deleted == 0),
        )
    )
    user_row = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user_row:
        return error_response(message="Token 无效", code=1251)
    permission_setting = user_row.permission_setting or {}
    raw_available = permission_setting.get("availableCount")
    available_count = None
    if raw_available is not None:
        try:
            available_count = int(raw_available)
        except (TypeError, ValueError):
            pass
    if available_count is not None and available_count > 0 and body.plannedCount > available_count:
        return error_response(message=f"建联人数超过权限上限（最多 {available_count} 人）", code=1252)

    shop_stmt = select(SellerTkShops).where(
        and_(
            SellerTkShops.id == body.shopId,
            SellerTkShops.user_id == user_id,
            SellerTkShops.deleted == 0,
        )
    )
    shop = (await db.execute(shop_stmt)).scalars().first()
    if not shop:
        return error_response(message="店铺不存在或无权限访问", code=400)

    is_immediate: bool
    scheduled_start_utc: datetime | None = None
    if body.startTime is None:
        is_immediate = True
    else:
        st = body.startTime
        if st.tzinfo is None:
            st = st.replace(tzinfo=timezone.utc)
        else:
            st = st.astimezone(timezone.utc)
        scheduled_start_utc = st
        now_min = now.replace(second=0, microsecond=0)
        start_min = st.replace(second=0, microsecond=0)
        if start_min < now_min:
            return error_response(message="启动时间已过期，请重新设置启动时间", code=400)
        is_immediate = start_min == now_min

    if is_immediate:
        plan_execute_time = int(now.timestamp())
        task_status = TaskStatus.RUNNING.value
        real_start_at = now
        saved_start_for_response = now
    else:
        if scheduled_start_utc is None:
            return error_response(message="启动时间无效", code=400)
        plan_execute_time = int(scheduled_start_utc.timestamp())
        task_status = TaskStatus.PENDING.value
        real_start_at = None
        saved_start_for_response = scheduled_start_utc

    message_ext = {
        "attachProducts": body.attachProducts,
        "productIds": body.productIds,
    }

    task_id = _uppercase_uuid()
    task = SellerTkOutreachSettings(
        id=task_id,
        user_id=user_id,
        shop_id=shop.id,
        shop_region_code=shop.shop_region_code,
        task_name=body.taskName,
        duplicate_check_type=body.duplicateCheckType,
        duplicate_check_code=body.duplicateCheckCode,
        message_send_strategy=_strategy_from_mode(body.outreachMode),
        task_type="OUTREACH",
        status=task_status,
        message=json.dumps(message_ext, ensure_ascii=False),
        search_keywords=(body.creatorFilter.keyword or "").strip() or None,
        filter_product_categories=body.creatorFilter.productCategories or None,
        filter_avg_commission_rate=body.creatorFilter.avgCommissionRate,
        filter_content_types=body.creatorFilter.contentTypes,
        filter_creator_agency=body.creatorFilter.creatorAgency,
        filter_fast_growth_list=_to_bit(body.creatorFilter.fastGrowing),
        filter_uninvited_creators_in_90_days=_to_bit(body.creatorFilter.notInvitedInPast90Days),
        filter_fans_age_range=body.creatorFilter.fansAgeRange or None,
        filter_fans_gender=body.creatorFilter.fansGender,
        filter_fans_count_range=body.creatorFilter.fansCountRange,
        filter_gmv_range=body.creatorFilter.gmvRange or None,
        filter_sales_count_range=body.creatorFilter.salesCountRange or None,
        filter_min_avg_video_views=body.creatorFilter.minAvgVideoViews,
        filter_min_avg_live_views=body.creatorFilter.minAvgLiveViews,
        filter_min_engagement_rate=body.creatorFilter.minEngagementRate,
        filter_creator_estimated_publish_rate=body.creatorFilter.creatorEstimatedPublishRate,
        filter_co_branding=body.creatorFilter.coBranding or None,
        filter_sort_by=body.creatorFilter.sortBy,
        first_message=body.firstMessage,
        second_message=body.replyMessage if body.outreachMode == "ALL" else None,
        plan_execute_time=plan_execute_time,
        expect_count=body.plannedCount,
        real_count=0,
        new_count=0,
        spend_time=0,
        real_start_at=real_start_at,
        creator_id=user_id,
        creation_time=now,
        last_modifier_id=user_id,
        last_modification_time=now,
    )

    db.add(task)
    scheduled_time = now if is_immediate else scheduled_start_utc
    filter_script = await _load_outreach_filter_script(
        db,
        region_code=shop.shop_region_code,
        shop_type=shop.shop_type,
    )
    filter_script_code, filter_script_version = await _register_outreach_filter_script(
        db,
        actor_id=user_id,
        region_code=shop.shop_region_code,
        shop_type=shop.shop_type,
        filter_script=filter_script,
    )
    task_payload = _build_outreach_task_payload(
        user_id=user_id,
        task=task,
        shop=shop,
        scheduled_time=scheduled_time,
        task_status=TaskStatus.PENDING.value,
        filter_script=filter_script,
        filter_script_code=filter_script_code,
        filter_script_version=filter_script_version,
    )
    await _upsert_outreach_rpa_plan(
        db,
        task_id=task_id,
        user_id=user_id,
        task_payload=task_payload,
        scheduled_time=scheduled_time,
        now=now,
    )

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        return error_response(message="新建建联任务失败", code=500)

    settings = get_settings(request)
    if is_immediate:
        await _dispatch_or_schedule_outreach_task_plan(
            settings=settings,
            task_id=task_id,
            user_id=user_id,
            task_payload=task_payload,
            scheduled_time=scheduled_time,
            now=now,
            dispatch_immediately=True,
            dispatch_failure_message="建联任务已创建但 seller inbox 通知失败",
            schedule_failure_message="建联任务加入新的 seller RPA 延迟中心失败",
            fallback_schedule_failure_message="建联任务通知失败后回退延迟中心也失败",
        )
    else:
        scheduled = await _dispatch_or_schedule_outreach_task_plan(
            settings=settings,
            task_id=task_id,
            user_id=user_id,
            task_payload=task_payload,
            scheduled_time=scheduled_time,
            now=now,
            dispatch_immediately=False,
            dispatch_failure_message="建联任务已创建但 seller inbox 通知失败",
            schedule_failure_message="建联任务加入新的 seller RPA 延迟中心失败",
        )
        if not scheduled:
            return error_response(message="任务已创建但加入新的延迟中心失败", code=500)

    return success_response(
        data=CreateOutreachTaskData(
            taskId=task_id,
            status=task_status,
            savedStartTime=saved_start_for_response,
        )
    )


@router.get(
    "/outreach/tasks/{task_id}",
    response_model=APIResponse[OutreachTaskDetailResponse],
    response_model_by_alias=True,
)
async def get_outreach_task(
    task_id: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
) -> APIResponse[OutreachTaskDetailResponse]:
    task_stmt = select(SellerTkOutreachSettings).where(
        and_(
            SellerTkOutreachSettings.id == task_id,
            SellerTkOutreachSettings.user_id == current_user_info.user_id,
        )
    )
    task = (await db.execute(task_stmt)).scalar_one_or_none()
    if not task:
        return error_response(message="任务不存在", code=404)

    attach_products, product_ids = _parse_message_ext(task.message)
    detail = OutreachTaskDetailResponse(
        taskId=task.id,
        shopId=task.shop_id,
        taskName=task.task_name,
        startTime=_start_time_from_epoch(task.plan_execute_time),
        creatorFilter=CreatorFilterDTO(
            keyword=task.search_keywords,
            productCategories=task.filter_product_categories or [],
            avgCommissionRate=task.filter_avg_commission_rate,
            contentTypes=task.filter_content_types,
            creatorAgency=task.filter_creator_agency,
            fastGrowing=_bit_to_bool(task.filter_fast_growth_list),
            notInvitedInPast90Days=_bit_to_bool(task.filter_uninvited_creators_in_90_days),
            fansAgeRange=task.filter_fans_age_range or [],
            fansGender=task.filter_fans_gender,
            fansCountRange=task.filter_fans_count_range,
            gmvRange=task.filter_gmv_range or [],
            salesCountRange=task.filter_sales_count_range or [],
            minAvgVideoViews=task.filter_min_avg_video_views,
            minAvgLiveViews=task.filter_min_avg_live_views,
            minEngagementRate=task.filter_min_engagement_rate,
            creatorEstimatedPublishRate=task.filter_creator_estimated_publish_rate,
            coBranding=task.filter_co_branding or [],
            sortBy=task.filter_sort_by if task.filter_sort_by is not None else 0,
        ),
        duplicateCheckType=task.duplicate_check_type,
        duplicateCheckCode=task.duplicate_check_code,
        plannedCount=task.expect_count or 0,
        outreachMode=_mode_from_strategy(task.message_send_strategy),
        firstMessage=task.first_message or "",
        replyMessage=task.second_message,
        attachProducts=attach_products,
        productIds=product_ids,
        status=_status_to_text(task.status),
        lastModificationTime=_to_utc(task.last_modification_time),
    )
    return success_response(data=detail)


@router.put(
    "/outreach/tasks/{task_id}",
    response_model=APIResponse[UpdateOutreachTaskData],
    response_model_by_alias=True,
)
async def update_outreach_task(
    request: Request,
    task_id: str,
    body: UpdateOutreachTaskRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
) -> APIResponse[UpdateOutreachTaskData]:
    user_id = current_user_info.user_id
    now = _to_millis_precision(datetime.now(timezone.utc))

    # 只允许编辑未启动任务
    task_stmt = select(SellerTkOutreachSettings).where(
        and_(
            SellerTkOutreachSettings.id == task_id,
            SellerTkOutreachSettings.user_id == user_id,
            SellerTkOutreachSettings.shop_id == body.shopId,
        )
    )
    task_row = (await db.execute(task_stmt)).scalar_one_or_none()
    if not task_row:
        return error_response(message="任务不存在", code=404)
    if str(task_row.status).upper() not in {TaskStatus.PENDING.value, "0"}:
        return error_response(message="任务已启动或已结束，不可编辑", code=409)

    # 配额校验
    user_stmt = select(IfIdentityUsers).where(
        and_(
            IfIdentityUsers.id == user_id,
            (IfIdentityUsers.deleted.is_(None)) | (IfIdentityUsers.deleted == 0),
        )
    )
    user_row = (await db.execute(user_stmt)).scalar_one_or_none()
    if not user_row:
        return error_response(message="Token 无效", code=1251)
    permission_setting = user_row.permission_setting or {}
    raw_available = permission_setting.get("availableCount")
    available_count = None
    if raw_available is not None:
        try:
            available_count = int(raw_available)
        except (TypeError, ValueError):
            pass
    if available_count is not None and available_count > 0 and body.plannedCount > available_count:
        return error_response(message=f"建联人数超过权限上限（最多 {available_count} 人）", code=400)

    # 启动时间校验
    if body.startTime is not None:
        start_time = _to_utc(body.startTime)
        now_min = now.replace(second=0, microsecond=0)
        start_min = start_time.replace(second=0, microsecond=0)
        if start_min <= now_min:
            return error_response(message="启动时间已过期，请重新设置启动时间", code=400)
        plan_execute_time = int(start_time.timestamp())
    else:
        plan_execute_time = None

    # last_modification_time 必须匹配
    expected_last_mod_time = _to_millis_precision(body.lastModificationTime)
    message_ext = {"attachProducts": body.attachProducts, "productIds": body.productIds}
    update_stmt = (
        update(SellerTkOutreachSettings)
        .where(
            and_(
                SellerTkOutreachSettings.id == task_id,
                SellerTkOutreachSettings.user_id == user_id,
                SellerTkOutreachSettings.shop_id == body.shopId,
                SellerTkOutreachSettings.last_modification_time == expected_last_mod_time,
                SellerTkOutreachSettings.status.in_([TaskStatus.PENDING.value, "0"]),
            )
        )
        .values(
            task_name=body.taskName,
            duplicate_check_type=body.duplicateCheckType,
            duplicate_check_code=body.duplicateCheckCode,
            message_send_strategy=_strategy_from_mode(body.outreachMode),
            message=json.dumps(message_ext, ensure_ascii=False),
            search_keywords=(body.creatorFilter.keyword or "").strip() or None,
            filter_product_categories=body.creatorFilter.productCategories or None,
            filter_avg_commission_rate=body.creatorFilter.avgCommissionRate,
            filter_content_types=body.creatorFilter.contentTypes,
            filter_creator_agency=body.creatorFilter.creatorAgency,
            filter_fast_growth_list=_to_bit(body.creatorFilter.fastGrowing),
            filter_uninvited_creators_in_90_days=_to_bit(body.creatorFilter.notInvitedInPast90Days),
            filter_fans_age_range=body.creatorFilter.fansAgeRange or None,
            filter_fans_gender=body.creatorFilter.fansGender,
            filter_fans_count_range=body.creatorFilter.fansCountRange,
            filter_gmv_range=body.creatorFilter.gmvRange or None,
            filter_sales_count_range=body.creatorFilter.salesCountRange or None,
            filter_min_avg_video_views=body.creatorFilter.minAvgVideoViews,
            filter_min_avg_live_views=body.creatorFilter.minAvgLiveViews,
            filter_min_engagement_rate=body.creatorFilter.minEngagementRate,
            filter_creator_estimated_publish_rate=body.creatorFilter.creatorEstimatedPublishRate,
            filter_co_branding=body.creatorFilter.coBranding or None,
            filter_sort_by=body.creatorFilter.sortBy,
            first_message=body.firstMessage,
            second_message=body.replyMessage if body.outreachMode == "ALL" else None,
            plan_execute_time=plan_execute_time,
            expect_count=body.plannedCount,
            last_modifier_id=user_id,
            last_modification_time=now,
        )
    )
    result = await db.execute(update_stmt)
    if (result.rowcount or 0) <= 0:
        await db.rollback()
        return error_response(message="任务已被更新，请刷新后重试", code=409)

    refreshed_task = (
        await db.execute(
            select(SellerTkOutreachSettings).where(
                SellerTkOutreachSettings.id == task_id,
                SellerTkOutreachSettings.user_id == user_id,
            )
        )
    ).scalar_one()
    shop_row = (
        await db.execute(
            select(SellerTkShops).where(
                SellerTkShops.id == body.shopId,
                SellerTkShops.user_id == user_id,
                SellerTkShops.deleted == 0,
            )
        )
    ).scalar_one()
    plan_scheduled_time = _start_time_from_epoch(refreshed_task.plan_execute_time) or now
    filter_script = await _load_outreach_filter_script(
        db,
        region_code=shop_row.shop_region_code,
        shop_type=shop_row.shop_type,
    )
    filter_script_code, filter_script_version = await _register_outreach_filter_script(
        db,
        actor_id=user_id,
        region_code=shop_row.shop_region_code,
        shop_type=shop_row.shop_type,
        filter_script=filter_script,
    )
    task_payload = _build_outreach_task_payload(
        user_id=user_id,
        task=refreshed_task,
        shop=shop_row,
        scheduled_time=plan_scheduled_time,
        task_status=TaskStatus.PENDING.value,
        filter_script=filter_script,
        filter_script_code=filter_script_code,
        filter_script_version=filter_script_version,
    )
    await _upsert_outreach_rpa_plan(
        db,
        task_id=task_id,
        user_id=user_id,
        task_payload=task_payload,
        scheduled_time=plan_scheduled_time,
        now=now,
    )
    await db.commit()
    settings = get_settings(request)
    if plan_scheduled_time <= now:
        await _dispatch_or_schedule_outreach_task_plan(
            settings=settings,
            task_id=task_id,
            user_id=user_id,
            task_payload=task_payload,
            scheduled_time=plan_scheduled_time,
            now=now,
            dispatch_immediately=True,
            dispatch_failure_message="编辑建联任务后 seller inbox 通知失败",
            schedule_failure_message="编辑建联任务后重新加入延迟中心失败",
            fallback_schedule_failure_message="编辑建联任务后通知失败且回退延迟中心失败",
        )
    else:
        await _dispatch_or_schedule_outreach_task_plan(
            settings=settings,
            task_id=task_id,
            user_id=user_id,
            task_payload=task_payload,
            scheduled_time=plan_scheduled_time,
            now=now,
            dispatch_immediately=False,
            dispatch_failure_message="编辑建联任务后 seller inbox 通知失败",
            schedule_failure_message="编辑建联任务后重新加入延迟中心失败",
        )

    return success_response(
        data=UpdateOutreachTaskData(
            taskId=task_id,
            lastModificationTime=now,
        )
    )


@router.post(
    "/outreach/tasks/{task_id}/start",
    response_model=APIResponse[StartOutreachTaskData],
    response_model_by_alias=True,
)
async def start_outreach_task(
    request: Request,
    task_id: str,
    body: StartOutreachTaskRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
) -> APIResponse[StartOutreachTaskData]:
    user_id = current_user_info.user_id
    now = _to_millis_precision(datetime.now(timezone.utc))

    task_stmt = select(SellerTkOutreachSettings).where(
        and_(
            SellerTkOutreachSettings.id == task_id,
            SellerTkOutreachSettings.user_id == user_id,
            SellerTkOutreachSettings.shop_id == body.shopId,
        )
    ).with_for_update()
    task_row = (await db.execute(task_stmt)).scalar_one_or_none()
    if not task_row:
        return error_response(message="任务不存在", code=404)

    expected_last_mod_time = _to_millis_precision(body.lastModificationTime)
    current_last_mod_time = _to_millis_precision(task_row.last_modification_time)
    if current_last_mod_time != expected_last_mod_time:
        await db.rollback()
        return error_response(message="任务已被更新，请刷新后重试", code=409)

    if str(task_row.status).upper() not in {TaskStatus.PENDING.value, "0"}:
        return error_response(message="任务已启动或已结束，不可重复启动", code=409)

    running_stmt = select(SellerTkOutreachSettings.id).where(
        and_(
            SellerTkOutreachSettings.shop_id == body.shopId,
            SellerTkOutreachSettings.id != task_id,
            SellerTkOutreachSettings.status.in_(list(_running_status_tokens())),
        )
    ).with_for_update()
    other_running = (await db.execute(running_stmt)).scalar_one_or_none()
    if other_running:
        return error_response(message="该店铺已有运行中的建联任务，请等待完成或结束后再启动", code=409)

    scheduled_time = now
    task_row.status = TaskStatus.RUNNING.value
    task_row.real_start_at = now
    task_row.plan_execute_time = int(now.timestamp())
    task_row.last_modifier_id = user_id
    task_row.last_modification_time = now

    shop_row = (
        await db.execute(
            select(SellerTkShops).where(
                SellerTkShops.id == body.shopId,
                SellerTkShops.user_id == user_id,
                SellerTkShops.deleted == 0,
            )
        )
    ).scalar_one_or_none()
    if shop_row is None:
        await db.rollback()
        return error_response(message="店铺不存在或无权限访问", code=404)
    filter_script = await _load_outreach_filter_script(
        db,
        region_code=shop_row.shop_region_code,
        shop_type=shop_row.shop_type,
    )
    filter_script_code, filter_script_version = await _register_outreach_filter_script(
        db,
        actor_id=user_id,
        region_code=shop_row.shop_region_code,
        shop_type=shop_row.shop_type,
        filter_script=filter_script,
    )
    task_payload = _build_outreach_task_payload(
        user_id=user_id,
        task=task_row,
        shop=shop_row,
        scheduled_time=scheduled_time,
        task_status=TaskStatus.PENDING.value,
        filter_script=filter_script,
        filter_script_code=filter_script_code,
        filter_script_version=filter_script_version,
    )
    await _upsert_outreach_rpa_plan(
        db,
        task_id=task_id,
        user_id=user_id,
        task_payload=task_payload,
        scheduled_time=scheduled_time,
        now=now,
    )

    await db.commit()
    settings = get_settings(request)
    await _dispatch_or_schedule_outreach_task_plan(
        settings=settings,
        task_id=task_id,
        user_id=user_id,
        task_payload=task_payload,
        scheduled_time=scheduled_time,
        now=now,
        dispatch_immediately=True,
        dispatch_failure_message="手动启动建联任务后 seller inbox 通知失败",
        schedule_failure_message="手动启动建联任务后重新加入延迟中心失败",
        fallback_schedule_failure_message="手动启动建联任务后通知失败且回退延迟中心失败",
    )

    return success_response(
        data=StartOutreachTaskData(
            taskId=task_id,
            status=TaskStatus.RUNNING.value,
            startTime=scheduled_time,
            lastModificationTime=now,
        )
    )


@router.post(
    "/outreach/tasks/{task_id}/end",
    response_model=APIResponse[EndOutreachTaskData],
    response_model_by_alias=True,
)
async def end_outreach_task(
    request: Request,
    task_id: str,
    body: EndOutreachTaskRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
) -> APIResponse[EndOutreachTaskData]:
    user_id = current_user_info.user_id
    now = _to_millis_precision(datetime.now(timezone.utc))

    task_stmt = select(SellerTkOutreachSettings).where(
        and_(
            SellerTkOutreachSettings.id == task_id,
            SellerTkOutreachSettings.user_id == user_id,
            SellerTkOutreachSettings.shop_id == body.shopId,
        )
    )
    task_row = (await db.execute(task_stmt)).scalar_one_or_none()
    if not task_row:
        return error_response(message="任务不存在", code=404)

    if str(task_row.status).upper() not in _running_status_tokens():
        return error_response(message="仅运行中的任务可结束", code=409)

    expected_last_mod_time = _to_millis_precision(body.lastModificationTime)
    spend_time = task_row.spend_time or 0
    if task_row.real_start_at is not None:
        real_start = _to_utc(task_row.real_start_at)
        spend_time = max(int((now - real_start).total_seconds()), 0)

    update_stmt = (
        update(SellerTkOutreachSettings)
        .where(
            and_(
                SellerTkOutreachSettings.id == task_id,
                SellerTkOutreachSettings.user_id == user_id,
                SellerTkOutreachSettings.shop_id == body.shopId,
                SellerTkOutreachSettings.last_modification_time == expected_last_mod_time,
                SellerTkOutreachSettings.status.in_(list(_running_status_tokens())),
            )
        )
        .values(
            status=TaskStatus.CANCELLED.value,
            real_end_at=now,
            spend_time=spend_time,
            last_modifier_id=user_id,
            last_modification_time=now,
        )
    )
    result = await db.execute(update_stmt)
    if (result.rowcount or 0) <= 0:
        await db.rollback()
        return error_response(message="任务已被更新，请刷新后重试", code=409)

    plan_row = (
        await db.execute(
            select(SellerTkRpaTaskPlans).where(
                SellerTkRpaTaskPlans.id == task_id,
                SellerTkRpaTaskPlans.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if plan_row is not None:
        plan_row.status = TaskStatus.CANCELLED.value
        plan_row.end_time = now
        plan_row.last_modifier_id = user_id
        plan_row.last_modification_time = now

    if plan_row is not None:
        settings = get_settings(request)
        notification_service = SellerRpaTaskNotificationService(settings)
        try:
            await notification_service.notify_task_cancelled(
                plan_row,
                payload={
                    "rootTaskId": task_id,
                    "cancelScope": "ROOT",
                },
            )
        except Exception as exc:
            logger.error("结束建联任务后 CANCEL_TASK 事件发送失败", exc_info=exc, task_id=task_id, user_id=user_id)

    await db.commit()
    if plan_row is not None:
        settings = get_settings(request)
        slot_dispatch_service = SellerRpaTaskSingleSlotDispatchService(db, settings)
        try:
            await slot_dispatch_service.dispatch_next_pending_task(
                user_id=user_id,
                task_type="OUTREACH",
            )
        except Exception:
            logger.error("结束建联任务后补发下一条 OUTREACH 失败", exc_info=True, task_id=task_id, user_id=user_id)

    return success_response(
        data=EndOutreachTaskData(
            taskId=task_id,
            status=TaskStatus.CANCELLED.value,
            endTime=now,
            lastModificationTime=now,
        )
    )
