"""
TikTok账号池管理路由
"""
from fastapi import APIRouter, Depends, HTTPException
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ..models.user import User
from ..auth.dependencies import get_current_user
from ..schemas import AccountsStatusResponse, AccountStatusItem

# 导入现有的账号池
from models.account_pool import get_account_pool

router = APIRouter(prefix="/api/accounts", tags=["账号管理"])


@router.get("/status", response_model=AccountsStatusResponse)
async def get_accounts_status(current_user: User = Depends(get_current_user)):
    """
    获取账号池状态

    需要登录才能访问。

    返回所有TikTok Shop账号的状态信息。
    """
    try:
        pool = get_account_pool()
        status = pool.get_status()

        accounts = [
            AccountStatusItem(
                id=acc["id"],
                name=acc["name"],
                email=acc["email"],
                region=acc["region"],
                status=acc["status"],
                usage_count=acc.get("usage_count", 0),
                using_tasks=acc.get("using_tasks", []),
            )
            for acc in status["accounts"]
        ]

        return AccountsStatusResponse(
            total=status["total"],
            available=status["available"],
            in_use=status["in_use"],
            accounts=accounts,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
