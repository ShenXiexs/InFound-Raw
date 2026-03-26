from fastapi import APIRouter

from apps.portal_seller_open_api.apis.endpoints import (
    creator_detail,
    outreach,
    sample_monitor,
    task,
)

open_api_router = APIRouter(prefix="", tags=["SELLER OPEN API"])
open_api_router.include_router(task.router)
open_api_router.include_router(outreach.router)
open_api_router.include_router(creator_detail.router)
open_api_router.include_router(sample_monitor.router)
