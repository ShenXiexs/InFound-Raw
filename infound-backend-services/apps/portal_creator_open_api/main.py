from pathlib import Path

from fastapi import FastAPI

from apps.portal_creator_open_api.apis.router import open_api_router
from apps.portal_creator_open_api.core.config import Settings
from apps.portal_creator_open_api.core.token_manager import TokenManager
from apps.portal_creator_open_api.middlewares.auth_filter_middleware import (
    AuthFilterMiddleware,
)
from core_base import SettingsFactory, get_logger
from core_redis import RedisClientManager
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

    async def startup_hook(self, app_temp: FastAPI):
        """资源初始化逻辑"""
        self.logger.info("执行服务【portal_creator_open_api】专属启动逻辑...")

        # 直接使用 self.settings，无需引用全局变量
        RedisClientManager.initialize(self.settings.redis)
        DatabaseManager.initialize(self.settings.mysql)

        app_temp.state.settings = self.settings
        app_temp.state.token_manager = TokenManager(self.settings)

    async def shutdown_hook(self, app_temp: FastAPI):
        """释放资源逻辑"""
        self.logger.info("执行服务【portal_creator_open_api】专属关闭逻辑...")  # 优雅关闭
        await DatabaseManager.close()
        RedisClientManager.close()

    def register_middlewares(self, app_temp: FastAPI):
        """注册中间件"""
        self.logger.info("注册【portal_creator_open_api】专属中间件")
        app_temp.add_middleware(AuthFilterMiddleware)

    def create_app(self) -> FastAPI:
        """工厂方法：组装并返回 FastAPI 实例"""
        app_temp = AppFactory.create_app(
            logger=self.logger,
            base_setting=self.settings,
            title="portal_creator_open_api",
            router=open_api_router,
            startup_hook=self.startup_hook,  # 传递实例方法
            shutdown_hook=self.shutdown_hook,
            register_custom_middlewares=self.register_middlewares,
        )
        return app_temp


# --- 实例化并运行 ---
launcher = ServiceLauncher()
app = launcher.create_app()
