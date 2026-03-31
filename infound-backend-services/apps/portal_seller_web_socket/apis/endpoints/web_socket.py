import anyio
from fastapi import APIRouter, WebSocket

from apps.portal_seller_web_socket.core.config import Settings
from core_base import get_logger
from shared_seller_application_services.current_user_info import CurrentUserInfo
from shared_seller_application_services.token_manager import TokenManager

router = APIRouter(tags=["WS"])
logger = get_logger()


@router.websocket("/stomp")
async def stomp_proxy(
        websocket: WebSocket
):
    """
    STOMP 透明代理服务

    功能：
    1. 接受 Electron 客户端的 WebSocket 连接
    2. 代理连接到 RabbitMQ Web STOMP
    3. 拦截并替换 CONNECT 帧（隐藏真实凭证）

    客户端完全感知不到 RabbitMQ 的存在
    """
    settings: Settings = getattr(websocket.app.state, "settings", None)
    if not settings:
        logger.error("Settings not initialized in app.state")
        await websocket.close(code=4000)
        return

    token_manager: TokenManager = getattr(websocket.app.state, "token_manager", None)
    if not token_manager:
        logger.error("TokenManager not initialized in app.state")
        await websocket.close(code=4000)
        return

    # 从 WebSocket headers 中获取 Token
    token = websocket.headers.get(settings.auth.required_header)
    if not token:
        logger.warning("Connection rejected: no token provided")
        await websocket.close(code=4003)
        return

    # 验证 Token 并解析用户信息
    payload: dict | None = token_manager.decode_access_token(token)
    if not payload:
        logger.warning("Connection rejected: invalid token")
        await websocket.close(code=4003)
        return

    username: str = payload.get('sub')
    token_jti: str = payload.get('jti')
    if not username or not token_jti:
        logger.warning("Connection rejected: token missing required fields")
        await websocket.close(code=4003)
        return

    # 检查 Token 是否在 Redis 中（未被登出）
    if not token_manager.is_token_valid_in_redis(username, token_jti):
        logger.warning("Connection rejected: token expired or logged out")
        await websocket.close(code=4003)
        return

    # 构建用户对象并存入 websocket.state
    current_user_info: CurrentUserInfo = token_manager.get_current_user_info(username, token_jti)
    if not current_user_info:
        logger.warning("Connection rejected: failed to get user info")
        await websocket.close(code=4003)
        return

    websocket.state.current_user_info = current_user_info

    # 2. 接受 WebSocket 连接
    await websocket.accept()
    logger.info(f"STOMP proxy connected - User ID: {current_user_info.user_id}")

    # 3. 获取 RabbitMQ 配置
    proxy = None

    try:
        # 4. 创建并初始化 STOMP 代理
        from apps.portal_seller_web_socket.core.stomp_proxy import STOMPProxy
        proxy = STOMPProxy(settings.rabbitmq_web_stomp, current_user_info)

        # 5. 连接到 RabbitMQ
        await proxy.connect_to_mq()

        # 6. 开启双向转发任务
        async with anyio.create_task_group() as tg:
            tg.start_soon(proxy.forward_to_mq, websocket)
            tg.start_soon(proxy.forward_to_client, websocket)

    except OSError as e:
        logger.error(f"Failed to connect to RabbitMQ: {e}")
        await websocket.close(code=4004)
    except Exception as e:
        logger.error(f"STOMP proxy error: {e}", exc_info=True)
        await websocket.close(code=4000)
    finally:
        # 7. 清理资源
        if proxy:
            try:
                await proxy.disconnect()
            except Exception:
                pass
        logger.info(f"STOMP proxy connection closed - User ID: {current_user_info.user_id}")
