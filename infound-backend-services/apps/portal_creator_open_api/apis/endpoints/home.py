from typing import Any

from fastapi import APIRouter

from core_base import APIResponse, success_response

router = APIRouter(tags=["首页"])


@router.get(
    "/",
    response_model=APIResponse[Any],
    response_model_by_alias=True,
)
async def index() -> APIResponse[Any]:
    return success_response(message="Hello INFound World")
