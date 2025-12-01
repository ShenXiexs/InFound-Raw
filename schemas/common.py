"""
通用数据模型
"""
from pydantic import BaseModel
from typing import Optional, Any

class Response(BaseModel):
    """统一响应格式"""
    success: bool
    message: Optional[str] = None
    data: Optional[Any] = None
