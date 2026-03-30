from pathlib import Path

from fastapi import FastAPI

from apps.portal_seller_web_socket.core.config import Settings
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
        """资源初始化逻辑"""
        self.logger.info("执行服务【portal_seller_web_socket】专属启动逻辑...")
        # 直接使用 self.settings，无需引用全局变量
        DatabaseManager.initialize(self.settings.mysql)
        RedisClientManager.initialize(self.settings.redis)

        app_temp.state.settings = self.settings
        app_temp.state.token_manager = TokenManager(self.settings.auth, self.settings.redis)

    async def shutdown_hook(self, app_temp: FastAPI):
        """释放资源逻辑"""
        self.logger.info("执行服务【portal_seller_web_socket】专属关闭逻辑...")

        await DatabaseManager.close()
        RedisClientManager.close()
        # await RabbitMQProducer.close()

    def register_middlewares(self, app_temp: FastAPI):
        """注册中间件"""
        self.logger.info("注册【portal_seller_web_socket】专属中间件")

    def create_app(self) -> FastAPI:
        """工厂方法：组装并返回 FastAPI 实例"""
        from apps.portal_seller_web_socket.apis.router import web_socket_router
        app_temp = AppFactory.create_app(
            logger=self.logger,
            base_setting=self.settings,
            title="portal_seller_web_socket",
            router=web_socket_router,
            startup_hook=self.startup_hook,  # 传递实例方法
            shutdown_hook=self.shutdown_hook,
            register_custom_middlewares=self.register_middlewares,
        )
        return app_temp


# --- 实例化并运行 ---
launcher = ServiceLauncher()
app = launcher.create_app()
