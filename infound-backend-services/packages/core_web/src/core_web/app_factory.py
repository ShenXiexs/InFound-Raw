import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from structlog.stdlib import BoundLogger

from core_web.base_web_config import BaseWebAppSettings
from core_web.exceptions import register_exception_handlers


class AppFactory:
    @staticmethod
    def create_app(
            logger: BoundLogger,
            base_setting: BaseWebAppSettings,
            title: str,
            router,
            startup_hook=None,
            shutdown_hook=None,
            register_custom_middlewares=None,
    ) -> FastAPI:
        logger.info(f"服务【{title}】启动中，环境：{base_setting.env}")

        @asynccontextmanager
        async def lifespan(app_temp: FastAPI):
            # 启动逻辑
            if startup_hook:
                (
                    await startup_hook(app_temp)
                    if asyncio.iscoroutinefunction(startup_hook)
                    else startup_hook(app_temp)
                )
            yield
            # 关闭逻辑
            if shutdown_hook:
                (
                    await shutdown_hook(app_temp)
                    if asyncio.iscoroutinefunction(shutdown_hook)
                    else shutdown_hook(app_temp)
                )

        app = FastAPI(
            title=title,
            description=f"{base_setting.app_name} - 环境：{base_setting.env}",
            version="1.0.0",
            docs_url="/docs" if base_setting.debug else None,
            redoc_url="/redoc" if base_setting.debug else None,
            lifespan=lifespan,
        )

        # 统一跨域配置
        app.add_middleware(
            CORSMiddleware,
            allow_origins=(
                ["*"] if base_setting.debug else base_setting.cors_allow_origins
            ),
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # 注册自定义中间件
        if register_custom_middlewares:
            register_custom_middlewares(app)

        # 统一异常处理
        register_exception_handlers(app)

        # 注入业务路由
        app.include_router(router)

        @app.get("/health")
        async def health():
            return {"status": "healthy", "service": title}

        return app
