"""
认证相关API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from schemas.auth import LoginResponse, UserResponse, RegisterRequest
from services.auth_service import AuthService
from api.deps import get_current_active_user
from utils.response import create_response

router = APIRouter()
auth_service = AuthService()

@router.post("/login", response_model=LoginResponse, summary="用户登录")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    用户登录获取Token
    - username: 用户名
    - password: 密码
    """
    user = auth_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = auth_service.create_token(user["username"])
    
    return LoginResponse(
        success=True,
        message="登录成功",
        data={
            "access_token": token,
            "token_type": "bearer",
            "user": UserResponse(**user)
        }
    )

@router.post("/register", summary="注册新用户(仅管理员)")
async def register(
    user_data: RegisterRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """
    注册新用户(需要管理员权限)
    """
    # 检查权限
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="权限不足")
    
    success, message = auth_service.create_user(
        username=user_data.username,
        password=user_data.password,
        role=user_data.role,
        email=user_data.email
    )
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return create_response(success=True, message=message)

@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_me(current_user: dict = Depends(get_current_active_user)):
    """获取当前登录用户信息"""
    return UserResponse(**current_user)
