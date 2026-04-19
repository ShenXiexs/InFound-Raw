from datetime import datetime, timezone, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.core.deps import get_db_session, get_settings
from apps.portal_seller_open_api.exceptions import raise_error, ErrorCodes
from apps.portal_seller_open_api.services.identity_user_service import (
    setup_user_stomp_queue,
)
from core_base import APIResponse, error_response, success_response
from shared_domain.models.infound import IfIdentityUsers
from shared_seller_application_services.current_user_info import CurrentUserInfo

router = APIRouter(tags=["用户"])


def _format_utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_reset_base_permission(now: datetime) -> dict[str, Any]:
    return {
        "availableDateRang": {
            "startDate": _format_utc_iso(now),
            "endDate": _format_utc_iso(now + timedelta(days=14)),
        },
        "maxShopCount": 2,
        "maxOutreachCountPerDay": 0,
        "maxRemindCreatorCountPerDay": 0,
        "enableExportCreatorData": False,
    }


def _parse_utc_iso(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ensure_permission_not_expired(user: IfIdentityUsers) -> bool:
    permission_setting = user.permission_setting or {}
    date_range = permission_setting.get("availableDateRang")
    if not isinstance(date_range, dict):
        return False
    end_date = _parse_utc_iso(date_range.get("endDate"))
    if end_date is None:
        return False
    now = datetime.now(timezone.utc)
    if now < end_date:
        return False
    user.permission_setting = _build_reset_base_permission(now)
    return True


def _build_user_payload(user: IfIdentityUsers) -> dict[str, Any]:
    user_type_str = str(user.user_type) if user.user_type is not None else "00"

    permission = user.permission_setting or {}
    default_permission = {
        "availableDateRang": {
            "startDate": "",
            "endDate": "",
        },
        "maxShopCount": 0,
        "maxOutreachCountPerDay": 0,
        "maxRemindCreatorCountPerDay": 0,
        "enableExportCreatorData": False,
        "enableDebug": False,
    }
    # 优先使用数据库中的值，缺失的字段用默认值
    final_permission = {**default_permission, **permission}

    return {
        "userId": user.id,
        "username": user.user_name,
        "phoneNumber": user.phone_number,
        "userType": user_type_str,
        "updateTime": _format_utc_iso(datetime.now(timezone.utc)),
        "permission": final_permission,
    }


@router.get(
    "/user/check-token",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def check_token(
        request: Request,
        db: Annotated[AsyncSession, Depends(get_db_session)],
        xunda_device_id: Annotated[str, Header(..., alias="xunda-device-id")],
) -> APIResponse[dict]:
    current_user_info: CurrentUserInfo = request.state.current_user_info
    if not current_user_info or not current_user_info.device_id:
        return error_response(message="Token 无效", code=1251)
    if current_user_info.device_id != xunda_device_id:
        return error_response(message="Token 无效", code=1251)

    sql = select(IfIdentityUsers).where(
        and_(
            IfIdentityUsers.id == current_user_info.user_id,
            (IfIdentityUsers.deleted.is_(None)) | (IfIdentityUsers.deleted == 0),
        )
    )
    user: IfIdentityUsers = (await db.execute(sql)).scalar_one_or_none()
    if not user:
        return error_response(message="Token 无效", code=1251)

    permission_changed = _ensure_permission_not_expired(user)
    if permission_changed:
        await db.commit()
        await db.refresh(user)

    return success_response(data=_build_user_payload(user))


@router.get(
    "/user/current",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def current_user(
        request: Request,
        db: Annotated[AsyncSession, Depends(get_db_session)],
) -> APIResponse[dict]:
    """获取当前用户信息"""
    if not hasattr(request.state, "current_user_info") or not request.state.current_user_info:
        raise HTTPException(status_code=401, detail="Unverified")

    current_user_info: CurrentUserInfo = request.state.current_user_info
    sql = select(IfIdentityUsers).where(
        and_(
            IfIdentityUsers.id == current_user_info.user_id,
            (IfIdentityUsers.deleted.is_(None)) | (IfIdentityUsers.deleted == 0),
        )
    )
    user: IfIdentityUsers = (await db.execute(sql)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="Unverified")

    permission_changed = _ensure_permission_not_expired(user)
    if permission_changed:
        await db.commit()
        await db.refresh(user)

    return success_response(data=_build_user_payload(user))


@router.get(
    "/user/test/stomp-queue-create",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def test_stomp_queue_create(
        request: Request,
        settings: Settings = Depends(get_settings),
) -> APIResponse[dict]:
    """获取当前用户信息"""
    if not hasattr(request.state, "current_user_info") or not request.state.current_user_info:
        raise HTTPException(status_code=401, detail="Unverified")

    current_user_info: CurrentUserInfo = request.state.current_user_info

    if not await setup_user_stomp_queue(current_user_info.user_id, settings.rabbitmq_web_stomp):
        raise raise_error("注册失败", ErrorCodes.INTERNAL_ERROR, status_code=500)

    return success_response(data={"message": "队列已经创建"})
