from fastapi import APIRouter

from apps.portal_creator_open_api.apis.endpoints import home, account
from apps.portal_creator_open_api.apis.endpoints import home, account, sample

# Service router (shared prefix)
open_api_router = APIRouter(prefix="", tags=["CREATOR OPEN API"])

# Register sub-routers
open_api_router.include_router(home.router)
open_api_router.include_router(account.router)
open_api_router.include_router(sample.router)
