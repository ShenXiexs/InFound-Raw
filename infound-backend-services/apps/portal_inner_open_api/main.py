from pathlib import Path
from typing import Optional

from fastapi import FastAPI

from apps.portal_inner_open_api.apis.router import open_api_router
from apps.portal_inner_open_api.core.config import Settings
from apps.portal_inner_open_api.core.rabbitmq_producer import RabbitMQProducer
from apps.portal_inner_open_api.middlewares.auth_filter_middleware import (
    AuthFilterMiddleware,
)
from apps.portal_inner_open_api.services import chatbot_schedule_publisher
from core_base import SettingsFactory, get_logger
from core_web import AppFactory
from shared_domain import DatabaseManager


class ServiceLauncher:
    def __init__(self):
        # 1. 初始化基础组件：配置与日志
        self.settings: Settings = SettingsFactory.initialize(
            settings_class=Settings,
            config_dir=Path(__file__).parent / "configs",
        )
        self.logger = get_logger()
        self.app: Optional[FastAPI] = None

    async def startup_hook(self, app_temp: FastAPI):
        """资源初始化逻辑"""
        self.logger.info("执行服务【portal_inner_open_api】专属启动逻辑...")
        # 直接使用 self.settings，无需引用全局变量
        DatabaseManager.initialize(self.settings.mysql)

        # 初始化 RabbitMQ 生产者
        try:
            await RabbitMQProducer.initialize()
        except Exception as e:
            self.logger.warning(
                "RabbitMQ 初始化失败（聊天机器人消息功能可能不可用）", error=str(e)
            )

        # 启动 chatbot schedule publisher（用于重复提醒/定时发送）
        if getattr(
                getattr(chatbot_schedule_publisher, "settings", None),
                "CHATBOT_SCHEDULE_PUBLISHER_ENABLED",
                True,
        ):
            try:
                await chatbot_schedule_publisher.start()
            except Exception as e:
                self.logger.warning(
                    "Chatbot schedule publisher 启动失败（重复提醒可能不可用）",
                    error=str(e),
                )

    async def shutdown_hook(self, app_temp: FastAPI):
        """释放资源逻辑"""
        self.logger.info("执行服务【portal_inner_open_api】专属关闭逻辑...")

        try:
            await chatbot_schedule_publisher.stop()
        except Exception:
            pass

        # 关闭 RabbitMQ 连接
        try:
            await RabbitMQProducer.close()
        except Exception:
            pass

    def register_middlewares(self, app_temp: FastAPI):
        """注册中间件"""
        self.logger.info("注册【portal_inner_open_api】专属中间件")
        app_temp.add_middleware(AuthFilterMiddleware)

    def create_app(self) -> FastAPI:
        """工厂方法：组装并返回 FastAPI 实例"""
        self.app = AppFactory.create_app(
            logger=self.logger,
            base_setting=self.settings,
            title="portal_inner_open_api",
            router=open_api_router,
            startup_hook=self.startup_hook,  # 传递实例方法
            shutdown_hook=self.shutdown_hook,
            register_custom_middlewares=self.register_middlewares,
        )
        return self.app


# --- 实例化并运行 ---
launcher = ServiceLauncher()
app = launcher.create_app()
