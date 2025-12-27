from fastapi import APIRouter

from .endpoints import home, sample, chatbot

# Service router (shared prefix)
open_api_router = APIRouter(prefix="", tags=["INNER OPEN API"])

# Register sub-routers
open_api_router.include_router(home.router)
open_api_router.include_router(sample.router)
open_api_router.include_router(chatbot.router)
