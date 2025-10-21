"""
认证路由 - 注册、登录、登出
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.user import User
from ..schemas import UserCreate, UserResponse, LoginRequest, LoginResponse
from ..auth import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    用户注册

    - **username**: 用户名（3-50字符）
    - **email**: 邮箱地址
    - **password**: 密码（至少6位）
    - **full_name**: 全名（可选）
    """
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    # 检查邮箱是否已存在
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱已被注册",
        )

    # 创建新用户
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        full_name=user_data.full_name,
        is_active=True,
        is_superuser=False,
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.post("/login", response_model=LoginResponse)
async def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    """
    用户登录

    - **username**: 用户名或邮箱
    - **password**: 密码

    返回：
    - **access_token**: JWT访问令牌
    - **token_type**: Bearer
    - **user**: 用户基本信息
    """
    # 查找用户（支持用户名或邮箱登录）
    user = (
        db.query(User)
        .filter(
            (User.username == login_data.username) | (User.email == login_data.username)
        )
        .first()
    )

    # 验证用户和密码
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 检查用户是否被禁用
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    # 生成 JWT token
    access_token = create_access_token(
        data={
            "user_id": user.id,
            "username": user.username,
        }
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "is_superuser": user.is_superuser,
        },
    )


@router.post("/logout")
async def logout():
    """
    用户登出

    注意：JWT 是无状态的，登出通常在前端删除 token 即可。
    后端可以实现 token 黑名单来真正失效 token（需要额外的存储）。
    """
    return {
        "success": True,
        "message": "登出成功，请在前端删除 token",
    }
