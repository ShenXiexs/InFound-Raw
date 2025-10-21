"""
认证相关的 Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional


class Token(BaseModel):
    """Token 响应"""
    access_token: str = Field(..., description="JWT 访问令牌")
    token_type: str = Field(default="bearer", description="Token 类型")


class TokenData(BaseModel):
    """Token 数据"""
    username: Optional[str] = None
    user_id: Optional[int] = None


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    token_type: str = "bearer"
    user: dict  # 用户基本信息


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱地址")
    password: str = Field(..., min_length=6, max_length=100, description="密码（至少6位）")
    full_name: Optional[str] = Field(None, description="全名")
