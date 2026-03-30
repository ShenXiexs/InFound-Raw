from fastapi import APIRouter

from core_base import APIResponse, success_response

router = APIRouter(tags=["首页"])


@router.get(
    "/",
    response_model=APIResponse[dict],
    response_model_by_alias=True,
)
async def home():
    """首页"""
    return success_response(data={"message": "XunDa Web Socket"})
