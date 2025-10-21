"""
用户相关的 Pydantic Schemas
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """用户基础Schema"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱地址")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")


class UserCreate(UserBase):
    """用户注册Schema"""
    password: str = Field(..., min_length=6, max_length=100, description="密码（至少6位）")


class UserUpdate(BaseModel):
    """用户更新Schema"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = Field(None, min_length=6, max_length=100)


class UserInDB(UserBase):
    """数据库中的用户Schema"""
    id: int
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True  # Pydantic v2 语法（原 orm_mode = True）


class UserResponse(UserBase):
    """用户响应Schema（隐藏敏感信息）"""
    id: int
    is_active: bool
    is_superuser: bool
    created_at: datetime

    class Config:
        from_attributes = True
