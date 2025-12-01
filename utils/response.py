"""
统一响应格式工具
"""
from typing import Any, Optional

def create_response(
    success: bool,
    message: Optional[str] = None,
    data: Optional[Any] = None
) -> dict:
    """
    创建统一格式的响应
    
    Args:
        success: 是否成功
        message: 提示信息
        data: 数据
    
    Returns:
        响应字典
    """
    response = {
        "success": success,
        "message": message or ("操作成功" if success else "操作失败"),
    }
    
    if data is not None:
        response["data"] = data
    
    return response
