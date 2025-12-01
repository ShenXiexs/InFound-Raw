"""
样品管理API
"""
from fastapi import APIRouter, Depends
from api.deps import get_current_active_user
from utils.response import create_response

router = APIRouter()

@router.get("/list", summary="获取样品列表")
async def list_samples(
    current_user: dict = Depends(get_current_active_user)
):
    """获取样品列表 - TODO: 实现"""
    return create_response(success=True, data={"message": "Sample功能待实现"})
