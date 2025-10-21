"""
任务相关的 Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class BrandConfig(BaseModel):
    """品牌配置"""
    name: str = Field(..., description="品牌名称")
    only_first: str = Field(default="0", description="是否只爬取第一页")
    key_word: Optional[str] = Field(None, description="关键词")


class TaskSubmitRequest(BaseModel):
    """任务提交请求"""
    region: str = Field(..., description="区域 (如: FR, MX)")
    brand: BrandConfig
    search_strategy: Dict[str, Any] = Field(..., description="搜索策略配置")
    email_first: Dict[str, Any] = Field(..., description="首次邮箱验证配置")
    email_later: Dict[str, Any] = Field(..., description="后续邮箱验证配置")


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    task_name: str
    status: str  # pending/running/completed/failed/cancelled
    start_time: Optional[str]
    end_time: Optional[str]
    total_creators: Optional[int]


class TaskSubmitResponse(BaseModel):
    """任务提交响应"""
    task_id: str
    brand_name: str
    region: str
    status: str
    message: str


class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: list[TaskStatusResponse]
    total: int


class AccountStatusItem(BaseModel):
    """账号状态项"""
    id: str
    name: str
    email: str
    region: str
    status: str
    usage_count: int
    using_tasks: list[str]


class AccountsStatusResponse(BaseModel):
    """账号池状态响应"""
    total: int
    available: int
    in_use: int
    accounts: list[AccountStatusItem]
