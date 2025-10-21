"""
统一响应格式
"""
from typing import Any, Optional
from fastapi.responses import JSONResponse


class APIResponse:
    """统一 API 响应格式"""

    @staticmethod
    def success(data: Any = None, message: str = "success", status_code: int = 200):
        """
        成功响应

        Args:
            data: 返回的数据
            message: 消息
            status_code: HTTP状态码

        Returns:
            JSONResponse
        """
        return JSONResponse(
            status_code=status_code,
            content={
                "success": True,
                "message": message,
                "data": data,
            },
        )

    @staticmethod
    def error(
        message: str = "error",
        error_code: Optional[str] = None,
        status_code: int = 400,
        details: Any = None,
    ):
        """
        错误响应

        Args:
            message: 错误消息
            error_code: 错误代码
            status_code: HTTP状态码
            details: 详细错误信息

        Returns:
            JSONResponse
        """
        content = {
            "success": False,
            "message": message,
        }

        if error_code:
            content["error_code"] = error_code

        if details:
            content["details"] = details

        return JSONResponse(status_code=status_code, content=content)
