"""
依赖注入 - 用于路由的依赖项
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from core.security import decode_access_token
from services.auth_service import AuthService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """获取当前登录用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    
    username: str = payload.get("sub")
    if username is None:
        raise credentials_exception
    
    # 验证用户是否存在
    auth_service = AuthService()
    user = auth_service.get_user(username)
    if user is None:
        raise credentials_exception
    
    return user

async def get_current_active_user(current_user: dict = Depends(get_current_user)) -> dict:
    """获取当前激活用户"""
    if not current_user.get("enabled", True):
        raise HTTPException(status_code=400, detail="用户已被禁用")
    return current_user
