from fastapi import APIRouter

from apps.portal_seller_web_socket.apis.endpoints import home, web_socket

# 服务路由（前缀统一管理）
web_socket_router = APIRouter(prefix="", tags=["XUNDA WEB SOCKET"])

# 注册子路由
web_socket_router.include_router(home.router)
web_socket_router.include_router(web_socket.router)
