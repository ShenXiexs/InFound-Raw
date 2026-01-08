from fastapi import FastAPI

from common.core.database import DatabaseManager
from common.core.logger import get_logger
from common.core.redis_client import RedisClientManager
from common.services.rabbitmq_producer import RabbitMQProducer

logger = get_logger()


async def startup_hook(app: FastAPI):
    """service-a 专属启动逻辑：加载限流中间件、扩展跨域规则"""
    logger.info("执行服务【portal_operation_open_api】专属启动逻辑...")
    RedisClientManager.initialize()
    DatabaseManager.initialize()

    # 初始化 RabbitMQ
    try:
        await RabbitMQProducer.initialize()
        logger.info("RabbitMQ 生产者已初始化")
    except Exception as e:
        logger.warning(f"RabbitMQ 初始化失败: {e}")


async def shutdown_hook(app: FastAPI):
    """service-a 专属关闭逻辑：释放资源"""
    logger.info("执行服务【portal_operation_open_api】专属关闭逻辑...")

    # 关闭 RabbitMQ 连接
    try:
        await RabbitMQProducer.close()
        logger.info("RabbitMQ 连接已关闭")
    except Exception as e:
        logger.warning(f"RabbitMQ 关闭失败: {e}")


def register_middlewares(app: FastAPI):
    """
    专门用来注册服务专属中间件：
    - 该函数在 create_app() 中调用，此时 app 还未启动（uvicorn.run() 之前）
    - 仅做中间件注册，不做资源初始化
    """
    logger.info("注册【portal_operation_open_api】专属中间件")
    # TODO: 注册中间件（如需要）
    pass
