from fastapi import APIRouter

from apps.portal_seller_open_api.apis.endpoints import (
    account,
    contract,
    contract_reminder,
    home,
    outreach,
    shop,
    task,
    user,
    rpa,
)

# 服务路由（前缀统一管理）
open_api_router = APIRouter(prefix="", tags=["XUNDA OPEN API"])

# 注册子路由
open_api_router.include_router(home.router)
open_api_router.include_router(account.router)
open_api_router.include_router(user.router)
open_api_router.include_router(shop.router)
open_api_router.include_router(outreach.router)
open_api_router.include_router(task.router)
open_api_router.include_router(contract.router)
open_api_router.include_router(contract_reminder.router)
open_api_router.include_router(rpa.router)
