from fastapi import FastAPI

from common.core.database import DatabaseManager
from common.core.logger import get_logger
from common.services.rabbitmq_producer import RabbitMQProducer
from apps.portal_inner_open_api.services.chatbot_schedule_publisher import (
    chatbot_schedule_publisher,
)
from .middlewares.request_filter_middleware import RequestFilterMiddleware

logger = get_logger()


async def startup_hook(app: FastAPI):
    """service-a 专属启动逻辑：加载限流中间件、扩展跨域规则"""
    logger.info("执行服务【portal_inner_open_api】专属启动逻辑，初始化数据库连接池...")
    DatabaseManager.initialize()
    
    # 初始化 RabbitMQ 生产者
    try:
        await RabbitMQProducer.initialize()
    except Exception as e:
        logger.warning(
            "RabbitMQ 初始化失败（聊天机器人消息功能可能不可用）",
            error=str(e)
        )

    # 启动 chatbot schedule publisher（用于重复提醒/定时发送）
    if getattr(getattr(chatbot_schedule_publisher, "settings", None), "CHATBOT_SCHEDULE_PUBLISHER_ENABLED", True):
        try:
            await chatbot_schedule_publisher.start()
        except Exception as e:
            logger.warning(
                "Chatbot schedule publisher 启动失败（重复提醒可能不可用）",
                error=str(e),
            )


async def shutdown_hook(app: FastAPI):
    """service-a 专属关闭逻辑：释放资源"""
    logger.info("执行服务【portal_inner_open_api】专属关闭逻辑...")

    try:
        await chatbot_schedule_publisher.stop()
    except Exception:
        pass
    
    # 关闭 RabbitMQ 连接
    try:
        await RabbitMQProducer.close()
    except Exception:
        pass


def register_middlewares(app: FastAPI):
    """
    专门用来注册服务专属中间件：
    - 该函数在 create_app() 中调用，此时 app 还未启动（uvicorn.run() 之前）
    - 仅做中间件注册，不做资源初始化
    """
    logger.info("注册【portal_inner_open_api】专属中间件")
    # 注册 Token 拦截中间件
    app.add_middleware(RequestFilterMiddleware)
