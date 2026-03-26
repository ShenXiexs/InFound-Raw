from typing import Any

from fastapi import APIRouter

from core_base import APIResponse, success_response

router = APIRouter(tags=["首页"])


@router.get("/")
async def index() -> APIResponse[Any]:
    return success_response(message="Hello INFound World")
