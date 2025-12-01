"""
聊天功能API
"""
from fastapi import APIRouter, Depends
from api.deps import get_current_active_user
from utils.response import create_response

router = APIRouter()

@router.get("/history", summary="获取聊天记录")
async def get_chat_history(
    current_user: dict = Depends(get_current_active_user)
):
    """获取聊天记录 - TODO: 实现"""
    return create_response(success=True, data={"message": "Chat功能待实现"})
