import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.core.deps import get_current_user_info, get_db_session
from apps.portal_seller_open_api.models.dtos.contract import (
    ContractReminderRecordListRequest,
    ContractRuleDetailData,
    ContractRuleListItem,
    SaveContractRuleRequest,
)
from core_base import APIResponse, error_response, success_response
from shared_domain.models.infound import (
    IfTkCreators,
    SellerTkContractMonitorLogs,
    SellerTkContractMonitorRules,
    SellerTkContractMonitors,
    SellerTkShops,
)
from shared_seller_application_services.current_user_info import CurrentUserInfo

router = APIRouter(tags=["履约"])

EXECUTION_EVENT = "SEND_MESSAGE_TO_CREATOR"


def _to_bit(value: bool) -> int:
    return 1 if value else 0


def _bit_is_true(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return int(value) != 0
    if isinstance(value, bytes):
        return value not in (b"", b"\x00")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "no"}:
            return False
        if normalized in {"1", "true", "yes"}:
            return True
    return bool(value)


def _is_configured_message(raw: str | None) -> bool:
    return bool((raw or "").strip())


async def _ensure_shop(
    db: AsyncSession,
    user_id: str,
    shop_id: str,
) -> bool:
    stmt = select(SellerTkShops.id).where(
        and_(
            SellerTkShops.id == shop_id,
            SellerTkShops.user_id == user_id,
            SellerTkShops.deleted == 0,
        )
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def _load_rule_by_code(
    db: AsyncSession,
    rule_code: str,
) -> SellerTkContractMonitorRules | None:
    stmt = select(SellerTkContractMonitorRules).where(
        SellerTkContractMonitorRules.code == rule_code,
    )
    return (await db.execute(stmt)).scalars().first()


async def _load_monitor(
    db: AsyncSession,
    user_id: str,
    shop_id: str,
    rule_code: str,
) -> SellerTkContractMonitors | None:
    stmt = (
        select(SellerTkContractMonitors)
        .where(
            and_(
                SellerTkContractMonitors.user_id == user_id,
                SellerTkContractMonitors.shop_id == shop_id,
                SellerTkContractMonitors.rule_code == rule_code,
            )
        )
        .order_by(SellerTkContractMonitors.last_modification_time.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


def _normalize_rule_code(rule_code: str) -> str:
    return (rule_code or "").strip()


@router.get(
    "/contract/rules",
    response_model=APIResponse[list[ContractRuleListItem]],
    response_model_by_alias=True,
    description="获取店铺规则配置列表",
)
async def list_contract_rules(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
    shop_id: str = Query(..., alias="shopId", description="店铺ID"),
) -> APIResponse[list[ContractRuleListItem]]:
    user_id = current_user_info.user_id
    shop_id = shop_id.strip()
    if not shop_id:
        return error_response(message="店铺 ID 无效", code=400)
    if not await _ensure_shop(db, user_id, shop_id):
        return error_response(message="店铺不存在", code=403)

    rules_stmt = select(SellerTkContractMonitorRules).order_by(
        SellerTkContractMonitorRules.id.asc()
    )
    rules = (await db.execute(rules_stmt)).scalars().all()

    monitors_stmt = (
        select(SellerTkContractMonitors)
        .where(
            and_(
                SellerTkContractMonitors.user_id == user_id,
                SellerTkContractMonitors.shop_id == shop_id,
            )
        )
        .order_by(SellerTkContractMonitors.last_modification_time.desc())
    )
    monitors_by_code: dict[str, SellerTkContractMonitors] = {}
    for m in (await db.execute(monitors_stmt)).scalars().all():
        if m.rule_code not in monitors_by_code:
            monitors_by_code[m.rule_code] = m

    items: list[ContractRuleListItem] = []
    for rule in rules:
        monitor = monitors_by_code.get(rule.code)
        msg = monitor.messagbe if monitor else None
        configured = _is_configured_message(msg)
        active = _bit_is_true(monitor.is_active) if monitor else False
        items.append(
            ContractRuleListItem(
                ruleCode=rule.code,
                name=rule.name,
                description=rule.description,
                remark=rule.remark,
                message=msg if configured else None,
                isConfigured=configured,
                isActive=active,
                canEnable=configured,
            )
        )

    return success_response(data=items)


@router.get(
    "/contract/rules/{rule_code}",
    response_model=APIResponse[ContractRuleDetailData],
    response_model_by_alias=True,
    description="获取单条规则详情",
)
async def get_contract_rule(
    rule_code: str,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
    shop_id: str = Query(..., alias="shopId", description="店铺ID"),
) -> APIResponse[ContractRuleDetailData]:
    rule_code = _normalize_rule_code(rule_code)
    if not rule_code:
        return error_response(message="规则编码无效", code=400)

    user_id = current_user_info.user_id
    shop_id = shop_id.strip()
    if not shop_id:
        return error_response(message="店铺 ID 无效", code=400)
    if not await _ensure_shop(db, user_id, shop_id):
        return error_response(message="店铺不存在", code=403)

    rule = await _load_rule_by_code(db, rule_code)
    if not rule:
        return error_response(message="规则不存在", code=404)

    monitor = await _load_monitor(db, user_id, shop_id, rule_code)
    msg = (monitor.messagbe if monitor else "") or ""
    active = _bit_is_true(monitor.is_active) if monitor else False

    return success_response(
        data=ContractRuleDetailData(
            ruleCode=rule.code,
            name=rule.name,
            description=rule.description,
            remark=rule.remark,
            executionEvent=EXECUTION_EVENT,
            message=msg,
            isActive=active,
        )
    )


@router.put(
    "/contract/rules/{rule_code}",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
    description="保存规则配置",
)
async def save_contract_rule(
    rule_code: str,
    body: SaveContractRuleRequest,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
) -> APIResponse[dict]:
    rule_code = _normalize_rule_code(rule_code)
    if not rule_code:
        return error_response(message="规则编码无效", code=400)

    user_id = current_user_info.user_id
    shop_id = body.shopId.strip()
    if not shop_id:
        return error_response(message="店铺 ID 无效", code=400)
    if not await _ensure_shop(db, user_id, shop_id):
        return error_response(message="店铺不存在", code=403)

    rule = await _load_rule_by_code(db, rule_code)
    if not rule:
        return error_response(message="规则不存在", code=404)

    now = datetime.now(timezone.utc)
    monitor = await _load_monitor(db, user_id, shop_id, rule_code)
    incoming_message = body.message
    incoming_enabled = bool(body.isActive)

    if incoming_enabled:
        effective_message = incoming_message
        if not _is_configured_message(effective_message) and monitor is not None:
            effective_message = monitor.messagbe
        if not _is_configured_message(effective_message):
            return error_response(message="不可启动，请先配置规则", code=409)

    if monitor is None:
        if incoming_message is None:
            return error_response(message="请先配置规则消息模板", code=409)
        monitor = SellerTkContractMonitors(
            id=str(uuid.uuid4()),
            user_id=user_id,
            shop_id=shop_id,
            rule_code=rule_code,
            messagbe=incoming_message,
            is_active=_to_bit(incoming_enabled),
            creator_id=user_id,
            creation_time=now,
            last_modifier_id=user_id,
            last_modification_time=now,
        )
        db.add(monitor)
    else:
        if incoming_message is not None:
            monitor.messagbe = incoming_message
        monitor.is_active = _to_bit(incoming_enabled)
        monitor.last_modifier_id = user_id
        monitor.last_modification_time = now

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        return error_response(message="保存规则配置失败", code=500)

    return success_response(data={"updated": True})


@router.post(
    "/contract/reminder-records",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
    description="履约提醒记录",
)
async def list_contract_reminder_records(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
    body: ContractReminderRecordListRequest = Body(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, alias="pageSize", ge=1, le=100),
) -> APIResponse[dict]:
    user_id = current_user_info.user_id
    shop_id = body.shopId.strip()
    if not shop_id:
        return error_response(message="店铺 ID 无效", code=400)
    if not await _ensure_shop(db, user_id, shop_id):
        return error_response(message="店铺不存在", code=403)

    base_stmt = (
        select(
            SellerTkContractMonitorLogs.id.label("id"),
            SellerTkContractMonitorLogs.rule_code.label("ruleCode"),
            IfTkCreators.platform_creator_display_name.label("creatorDisplayName"),
            IfTkCreators.followers.label("followers"),
            IfTkCreators.sales_revenue.label("gmv"),
            SellerTkContractMonitorLogs.creation_time.label("remindAt"),
        )
        .select_from(SellerTkContractMonitorLogs)
        .outerjoin(
            IfTkCreators,
            IfTkCreators.platform_creator_id == SellerTkContractMonitorLogs.platform_creator_id,
        )
        .where(
            and_(
                SellerTkContractMonitorLogs.user_id == user_id,
                SellerTkContractMonitorLogs.shop_id == shop_id,
            )
        )
    )

    normalized_rule_code = (body.ruleCode or "").strip()
    if normalized_rule_code:
        base_stmt = base_stmt.where(
            SellerTkContractMonitorLogs.rule_code == normalized_rule_code.upper()
        )

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    total = int((await db.execute(count_stmt)).scalar() or 0)

    offset = (page - 1) * page_size
    page_stmt = (
        base_stmt.order_by(
            SellerTkContractMonitorLogs.creation_time.desc(),
            SellerTkContractMonitorLogs.id.desc(),
        )
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(page_stmt)).mappings().all()

    items: list[dict] = []
    for r in rows:
        display_name = r.get("creatorDisplayName")
        gmv = r.get("gmv")
        items.append(
            {
                "id": r.get("id"),
                "creator": display_name,
                "followers": r.get("followers"),
                "gmv": float(gmv) if gmv is not None else None,
                "hitRule": r.get("ruleCode"),
                "remindAt": r.get("remindAt"),
            }
        )

    return success_response(
        data={
            "total": total,
            "page": page,
            "pageSize": page_size,
            "items": items,
        }
    )


@router.get(
    "/contract/reminder-records/last-24h-count",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
    description="过去24小时内提醒达人数量",
)
async def count_contract_reminder_creators_last_24h(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    current_user_info: CurrentUserInfo = Depends(get_current_user_info),
    shop_id: str = Query(..., alias="shopId", min_length=1, description="店铺ID"),
) -> APIResponse[dict]:
    user_id = current_user_info.user_id
    shop_id = shop_id.strip()
    if not shop_id:
        return error_response(message="店铺 ID 无效", code=400)
    if not await _ensure_shop(db, user_id, shop_id):
        return error_response(message="店铺不存在", code=403)

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    stmt = select(func.count(func.distinct(SellerTkContractMonitorLogs.platform_creator_id))).where(
        and_(
            SellerTkContractMonitorLogs.user_id == user_id,
            SellerTkContractMonitorLogs.shop_id == shop_id,
            SellerTkContractMonitorLogs.creation_time >= since,
        )
    )
    count_value = int((await db.execute(stmt)).scalar() or 0)
    return success_response(data={"count": count_value})
