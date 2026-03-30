import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.app_constants import HEADER_DEVICE_ID
from apps.portal_seller_open_api.core.deps import get_db_session, get_current_user_info
from apps.portal_seller_open_api.models.dtos.shop import (
    AddShopRequest,
    DeleteShopRequest,
    OpenShopRequest,
    UpdateShopRequest,
    ShopEntry,
    ShopListItem,
)
from core_base import APIResponse, error_response, success_response
from shared_domain.models.infound import SellerTkShopPlatformSettings, SellerTkShops
from shared_seller_application_services.current_user_info import CurrentUserInfo

router = APIRouter(tags=["店铺"])


@router.post(
    "/shop/add",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def add_shop(
        body: AddShopRequest,
        db: Annotated[AsyncSession, Depends(get_db_session)],
        current_user_info: CurrentUserInfo = Depends(get_current_user_info),
) -> APIResponse[dict]:
    """添加店铺信息"""
    platform_stmt = select(SellerTkShopPlatformSettings).where(
        and_(
            SellerTkShopPlatformSettings.id == body.entryId,
            SellerTkShopPlatformSettings.is_active == 1,
        )
    )
    platform_result = await db.execute(platform_stmt)
    platform_setting = platform_result.scalar_one_or_none()
    if not platform_setting:
        return error_response(message="未找到匹配的店铺平台配置", code=400)

    now = datetime.now(timezone.utc)
    user_id = current_user_info.user_id

    new_shop = SellerTkShops(
        id=str(uuid.uuid4()),
        user_id=user_id,
        shop_type=platform_setting.shop_type,
        shop_region_code=platform_setting.region_code,
        shop_name=body.name,
        shop_entry_id=body.entryId,
        shop_remark=body.remark,
        deleted=0,
        creator_id=user_id,
        creation_time=now,
        last_modifier_id=user_id,
        last_modification_time=now,
    )

    db.add(new_shop)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        return error_response(message="新增店铺失败", code=500)

    return success_response()


@router.get(
    "/shop/entries",
    response_model=APIResponse[list[ShopEntry]],
    response_model_by_alias=True,
)
async def list_shop_entries(
        db: Annotated[AsyncSession, Depends(get_db_session)],
) -> APIResponse[list[ShopEntry]]:
    """获取可用的店铺登录入口列表"""
    stmt = select(SellerTkShopPlatformSettings).where(SellerTkShopPlatformSettings.is_active == 1)
    result = await db.execute(stmt)
    entries = result.scalars().all()

    data = [
        ShopEntry(
            entryId=entry.id,
            regionCode=entry.region_code,
            regionName=entry.region_name,
            shopType=entry.shop_type,
            loginUrl=entry.login_url,
        )
        for entry in entries
    ]

    return success_response(data=data)


@router.get(
    "/shop/list",
    response_model=APIResponse[list[ShopListItem]],
    response_model_by_alias=True,
)
async def list_shops(
        db: Annotated[AsyncSession, Depends(get_db_session)],
        current_user_info: CurrentUserInfo = Depends(get_current_user_info),
) -> APIResponse[list[ShopListItem]]:
    """获取当前登录用户的店铺列表"""
    stmt = (
        select(
            SellerTkShops.id,
            SellerTkShops.shop_name,
            SellerTkShops.shop_region_code,
            SellerTkShops.shop_type,
            SellerTkShops.shop_remark,
            SellerTkShops.shop_last_open_at,
            SellerTkShopPlatformSettings.region_name,
            SellerTkShopPlatformSettings.login_url,
        )
        .select_from(SellerTkShops)
        .join(
            SellerTkShopPlatformSettings,
            SellerTkShopPlatformSettings.id == SellerTkShops.shop_entry_id,
            isouter=True,
        )
        .where(
            and_(
                SellerTkShops.user_id == current_user_info.user_id,
                SellerTkShops.deleted == 0,
            )
        )
        .order_by(SellerTkShops.creation_time.desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    data: list[ShopListItem] = [
        ShopListItem(
            id=row.id,
            name=row.shop_name,
            regionCode=row.shop_region_code,
            regionName=row.region_name or "",
            shopType=row.shop_type,
            loginUrl=row.login_url or "",
            remark=row.shop_remark or "",
            shopLastOpen=row.shop_last_open_at,
        )
        for row in rows
    ]

    return success_response(data=data)


@router.post(
    "/shop/open",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def open_shop(
        request: Request,
        body: OpenShopRequest,
        db: Annotated[AsyncSession, Depends(get_db_session)],
) -> APIResponse[dict]:
    """记录店铺打开时间"""
    current_user_info: CurrentUserInfo | None = getattr(request.state, "current_user_info", None)
    if not current_user_info or not current_user_info.user_id:
        return error_response(message="Token 无效", code=1251)

    now = datetime.now(timezone.utc)
    user_id = current_user_info.user_id

    stmt = (
        update(SellerTkShops)
        .where(
            and_(
                SellerTkShops.id == body.id,
                SellerTkShops.user_id == user_id,
                SellerTkShops.deleted == 0,
            )
        )
        .values(
            shop_last_open_at=now,
            last_modifier_id=user_id,
            last_modification_time=now,
        )
    )

    try:
        result = await db.execute(stmt)
        if (result.rowcount or 0) <= 0:
            await db.rollback()
            return error_response(message="未找到匹配的店铺", code=404)
        await db.commit()
    except Exception:
        await db.rollback()
        return error_response(message="更新店铺打开时间失败", code=500)

    return success_response()


@router.post(
    "/shop/delete",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def delete_shop(
        request: Request,
        body: DeleteShopRequest,
        db: Annotated[AsyncSession, Depends(get_db_session)],
) -> APIResponse[dict]:
    """删除店铺（软删除）"""
    current_user_info: CurrentUserInfo | None = getattr(request.state, "current_user_info", None)
    if not current_user_info or not current_user_info.user_id:
        return error_response(message="Token 无效", code=1251)

    now = datetime.now(timezone.utc)
    user_id = current_user_info.user_id

    stmt = (
        update(SellerTkShops)
        .where(
            and_(
                SellerTkShops.id == body.id,
                SellerTkShops.user_id == user_id,
                SellerTkShops.deleted == 0,
            )
        )
        .values(
            deleted=1,
            last_modifier_id=user_id,
            last_modification_time=now,
        )
    )

    try:
        result = await db.execute(stmt)
        if (result.rowcount or 0) <= 0:
            await db.rollback()
            return error_response(message="未找到匹配的店铺", code=404)
        await db.commit()
    except Exception:
        await db.rollback()
        return error_response(message="删除店铺失败", code=500)

    return success_response()


@router.put(
    "/shop/update",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def update_shop(
        request: Request,
        body: UpdateShopRequest,
        db: Annotated[AsyncSession, Depends(get_db_session)],
        xunda_device_id: Annotated[str, Header(..., alias=HEADER_DEVICE_ID)],
) -> APIResponse[dict]:
    """修改店铺信息"""
    current_user_info: CurrentUserInfo | None = getattr(request.state, "current_user_info", None)
    if not current_user_info or not current_user_info.device_id or not current_user_info.user_id:
        return error_response(message="Token 无效", code=1251)
    if current_user_info.device_id != xunda_device_id:
        return error_response(message="Token 无效", code=1251)

    if body.name is None and body.remark is None and body.entryId is None:
        return error_response(message="请至少传入一个需要修改的字段", code=400)

    now = datetime.now(timezone.utc)
    user_id = current_user_info.user_id

    values: dict = {
        "last_modifier_id": user_id,
        "last_modification_time": now,
    }

    if body.name is not None:
        values["shop_name"] = body.name
    if body.remark is not None:
        values["shop_remark"] = body.remark
    if body.entryId is not None:
        platform_stmt = select(SellerTkShopPlatformSettings).where(
            and_(
                SellerTkShopPlatformSettings.id == body.entryId,
                SellerTkShopPlatformSettings.is_active == 1,
            )
        )
        platform_result = await db.execute(platform_stmt)
        platform_setting = platform_result.scalar_one_or_none()
        if not platform_setting:
            return error_response(message="未找到匹配的店铺平台配置", code=400)

        values["shop_entry_id"] = body.entryId
        values["shop_type"] = platform_setting.shop_type
        values["shop_region_code"] = platform_setting.region_code

    stmt = (
        update(SellerTkShops)
        .where(
            and_(
                SellerTkShops.id == body.id,
                SellerTkShops.user_id == user_id,
                SellerTkShops.deleted == 0,
            )
        )
        .values(**values)
    )

    try:
        result = await db.execute(stmt)
        if (result.rowcount or 0) <= 0:
            await db.rollback()
            return error_response(message="未找到匹配的店铺", code=404)
        await db.commit()
    except Exception:
        await db.rollback()
        return error_response(message="修改店铺失败", code=500)

    return success_response()
