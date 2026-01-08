from fastapi import APIRouter

from .endpoints import home, sample, chatbot, creator, outreach_task

# 服务路由（前缀统一管理）
open_api_router = APIRouter(prefix="", tags=["INNER OPEN API"])

# 注册子路由
open_api_router.include_router(home.router)
open_api_router.include_router(sample.router)
open_api_router.include_router(chatbot.router)
open_api_router.include_router(creator.router)
open_api_router.include_router(outreach_task.router)
