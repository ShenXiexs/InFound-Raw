"""
认证依赖注入
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..models.user import User
from .jwt_handler import decode_access_token

# HTTP Bearer 认证方案
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """
    获取当前登录用户

    用法：
    @app.get("/protected")
    def protected_route(current_user: User = Depends(get_current_user)):
        return {"user": current_user.username}
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 解码 token
    token = credentials.credentials
    payload = decode_access_token(token)

    if payload is None:
        raise credentials_exception

    # 获取用户ID
    user_id: Optional[int] = payload.get("user_id")
    if user_id is None:
        raise credentials_exception

    # 从数据库查询用户
    user = db.query(User).filter(User.id == user_id).first()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    获取当前激活的用户（仅激活用户可访问）

    用法：
    @app.get("/active-only")
    def active_only_route(current_user: User = Depends(get_current_active_user)):
        return {"user": current_user.username}
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户未激活",
        )
    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    获取当前超级管理员（仅超级管理员可访问）

    用法：
    @app.delete("/admin/users/{user_id}")
    def delete_user(user_id: int, admin: User = Depends(get_current_superuser)):
        ...
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足，需要管理员权限",
        )
    return current_user
