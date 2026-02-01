from typing import Any

from fastapi import APIRouter

from common.core.response import success_response, APIResponse

router = APIRouter(tags=["首页"])


@router.get("/")
async def index() -> APIResponse[Any]:
    return success_response(message="Hello INFound World")
