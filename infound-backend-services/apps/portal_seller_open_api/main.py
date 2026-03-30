from pathlib import Path

from fastapi import FastAPI

from apps.portal_seller_open_api.apis.router import open_api_router
from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.core.rabbitmq_producer import RabbitMQProducer
from apps.portal_seller_open_api.middlewares.auth_filter_middleware import AuthFilterMiddleware
from apps.portal_seller_open_api.services.scheduler_service import (
    SellerRpaSchedulerService,
)
from core_base import SettingsFactory, get_logger
from core_redis import RedisClientManager
from core_web import AppFactory
from shared_domain import DatabaseManager
from shared_seller_application_services.token_manager import TokenManager


class ServiceLauncher:
    def __init__(self):
        # 1. 初始化基础组件：配置与日志
        self.settings: Settings = SettingsFactory.initialize(
            settings_class=Settings,
            config_dir=Path(__file__).parent / "configs",
        )
        self.logger = get_logger()

    async def startup_hook(self, app_temp: FastAPI):
        self.logger.info("执行服务【portal_seller_open_api】专属启动逻辑...")
        DatabaseManager.initialize(self.settings.mysql)
        RedisClientManager.initialize(self.settings.redis)

        app_temp.state.settings = self.settings
        app_temp.state.token_manager = TokenManager(self.settings.auth, self.settings.redis)
        app_temp.state.scheduler_service = SellerRpaSchedulerService(self.settings)
        await app_temp.state.scheduler_service.start()

    async def shutdown_hook(self, app_temp: FastAPI):
        self.logger.info("执行服务【portal_seller_open_api】专属关闭逻辑...")
        scheduler_service = getattr(app_temp.state, "scheduler_service", None)
        if scheduler_service is not None:
            await scheduler_service.stop()
        await RabbitMQProducer.close()
        await DatabaseManager.close()
        RedisClientManager.close()

    def register_middlewares(self, app_temp: FastAPI):
        self.logger.info("注册【portal_seller_open_api】专属中间件")
        app_temp.add_middleware(AuthFilterMiddleware)

    def create_app(self) -> FastAPI:
        return AppFactory.create_app(
            logger=self.logger,
            base_setting=self.settings,
            title="portal_seller_open_api",
            router=open_api_router,
            startup_hook=self.startup_hook,
            shutdown_hook=self.shutdown_hook,
            register_custom_middlewares=self.register_middlewares,
        )
launcher = ServiceLauncher()
app = launcher.create_app()
