from fastapi import APIRouter

from apps.portal_creator_open_api.apis.endpoints import home, account
from apps.portal_creator_open_api.apis.endpoints import home, account, sample

# 服务路由（前缀统一管理）
open_api_router = APIRouter(prefix="", tags=["CREATOR OPEN API"])

# 注册子路由
open_api_router.include_router(home.router)
open_api_router.include_router(account.router)
open_api_router.include_router(sample.router)
