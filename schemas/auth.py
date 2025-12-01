"""
认证相关数据模型
"""
from pydantic import BaseModel, EmailStr
from typing import Optional

class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str

class RegisterRequest(BaseModel):
    """注册请求"""
    username: str
    password: str
    email: Optional[EmailStr] = None
    role: str = "user"

class UserResponse(BaseModel):
    """用户响应"""
    username: str
    email: Optional[str] = None
    role: str
    enabled: bool = True
    created_at: Optional[str] = None

class TokenData(BaseModel):
    """Token数据"""
    access_token: str
    token_type: str
    user: UserResponse

class LoginResponse(BaseModel):
    """登录响应"""
    success: bool
    message: str
    data: TokenData
