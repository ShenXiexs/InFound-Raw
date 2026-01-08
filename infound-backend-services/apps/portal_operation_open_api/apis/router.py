from fastapi import APIRouter

from apps.portal_operation_open_api.apis.endpoints import outreach_task, home, crawler_task, auth

# ⚠️ main.py 通过反射获取，名字必须是 open_api_router
open_api_router = APIRouter()

# 注册本服务的所有 endpoint
open_api_router.include_router(home.router)
open_api_router.include_router(auth.router)
# open_api_router.include_router(outreach_task.router)  # 已合并到 crawler_task.router
open_api_router.include_router(crawler_task.router)
