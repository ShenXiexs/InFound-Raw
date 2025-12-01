"""
认证中间件
"""
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)

class AuthMiddleware(BaseHTTPMiddleware):
    """认证中间件"""
    
    async def dispatch(self, request: Request, call_next):
        # 公开路径,不需要认证
        public_paths = [
            "/",
            "/health",
            "/docs",
            "/openapi.json",
            "/api/v1/auth/login",
        ]
        
        if request.url.path in public_paths:
            return await call_next(request)
        
        # 其他路径的认证由各个路由的Depends处理
        response = await call_next(request)
        return response
