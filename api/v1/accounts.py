"""
账号池管理API
"""
from fastapi import APIRouter, Depends, HTTPException
from models.account_pool import get_account_pool
from api.deps import get_current_active_user
from utils.response import create_response

router = APIRouter()

@router.get("/status", summary="获取账号池状态")
async def get_account_status(
    current_user: dict = Depends(get_current_active_user)
):
    """获取账号池状态"""
    pool = get_account_pool()
    status = pool.get_status()
    return create_response(success=True, data=status)

@router.get("/list", summary="获取账号列表")
async def list_accounts(
    current_user: dict = Depends(get_current_active_user)
):
    """获取账号列表"""
    pool = get_account_pool()
    status = pool.get_status()
    return create_response(success=True, data=status["accounts"])

@router.post("/reload", summary="重新加载账号配置")
async def reload_accounts(
    current_user: dict = Depends(get_current_active_user)
):
    """重新加载账号配置文件"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="权限不足")
    
    pool = get_account_pool()
    pool.reload_config()
    return create_response(success=True, message="账号配置已重新加载")
