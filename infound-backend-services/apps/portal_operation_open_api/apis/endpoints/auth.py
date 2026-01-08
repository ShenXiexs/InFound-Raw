from fastapi import APIRouter, Query

from common.core.response import success_response
from apps.portal_operation_open_api.models.auth import LoginRequest


router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


@router.post("/login")
async def login(
    payload: LoginRequest,
    body: str | None = Query(None, description="Body parameter"),
    password: str | None = Query(None, description="Password parameter"),
):
    """
    用户登录
    """
    # 当前阶段：只做参数接收 & 联调
    return success_response({
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example",
        "username": payload.username
    })
