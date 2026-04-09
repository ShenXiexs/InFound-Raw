import asyncio
from contextlib import asynccontextmanager
from importlib import import_module

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from packages.shared_infrastructure.src.shared_infrastructure.logger import (
    get_logger,
    initialize_logging,
)

from common.core.config import initialize_settings, get_settings
from common.core.exceptions import register_exception_handlers
from common.core.startup import default_startup_hook, default_shutdown_hook
from core_base.api_response import success_response

initialize_settings()
settings = get_settings()

initialize_logging()
logger = get_logger()


# 动态导入服务路由和专属钩子
def import_service_components(service_name: str):
    """
    动态导入服务的 3 个核心组件：
    1. 路由 router
    2. 启动钩子 startup_hook
    3. 关闭钩子 shutdown_hook
    """
    try:
        # 导入路由（如 apps.service-a.router.api_v1_router）
        router_module = import_module(f"apps.{service_name}.apis.router")
        router = getattr(router_module, f"open_api_router")

        # 导入专属启动/关闭钩子（若服务未定义，使用默认空钩子）
        try:
            startup_module = import_module(f"apps.{service_name}.startup")
            # 中间件注册函数（接收 app 实例，注册专属中间件）
            register_middlewares = getattr(startup_module, "register_middlewares", None)
            startup_hook = getattr(startup_module, "startup_hook")
            shutdown_hook = getattr(startup_module, "shutdown_hook")
        except (ImportError, AttributeError):
            logger.warning(f"服务 {service_name} 未定义专属启动/关闭钩子，使用默认逻辑")
            register_middlewares = None
            startup_hook = default_startup_hook
            shutdown_hook = default_shutdown_hook

        return router, register_middlewares, startup_hook, shutdown_hook
    except (ImportError, AttributeError) as e:
        logger.error(f"导入服务 {service_name} 组件失败", exc_info=True)
        raise ValueError(f"服务 {service_name} 配置错误：{str(e)}") from e


def create_app() -> FastAPI:
    """创建应用实例：通用逻辑 + 服务专属逻辑"""
    logger.info(f"服务【{settings.service_name}】开始启动，环境：{settings.env}")

    # 1. 动态导入服务组件（路由 + 专属钩子）
    (
        service_router,
        service_register_middlewares,
        service_startup_hook,
        service_shutdown_hook,
    ) = import_service_components(settings.service_name)

    # 2. 使用 lifespan 管理生命周期事件
    @asynccontextmanager
    async def lifespan(app_local: FastAPI):
        # 调用服务专属启动逻辑（初始化资源）
        if asyncio.iscoroutinefunction(service_startup_hook):
            await service_startup_hook(app_local)
        else:
            service_startup_hook(app_local)
        yield
        # 调用服务专属关闭逻辑（释放资源）
        if asyncio.iscoroutinefunction(service_shutdown_hook):
            await service_shutdown_hook(app_local)
        else:
            service_shutdown_hook(app_local)

    # 3. 基础初始化（所有服务共用）
    app_temp = FastAPI(
        title=settings.app_name,
        description=f"{settings.app_name} - 服务：{settings.service_name} - 环境：{settings.env}",
        version="1.0.0",
        docs_url=f"/v1/docs" if settings.debug else None,
        redoc_url=f"/v1/redoc" if settings.debug else None,
        lifespan=lifespan,
    )
    app_temp.state.debug = settings.debug

    # 4. 跨域中间件（开发环境允许所有跨域）
    if settings.debug:
        app_temp.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # CORS配置
        app_temp.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ALLOW_ORIGINS,
            allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    if service_register_middlewares:
        service_register_middlewares(app_temp)

    # 5. 注册异常处理器
    register_exception_handlers(app_temp)

    # 6. 注册服务路由（通用逻辑）
    app_temp.include_router(service_router)

    return app_temp


app = create_app()


@app.get(f"/health")
async def health_check():
    return success_response(
        {
            "status": "healthy",
            "service_name": settings.service_name,
            "env": settings.env,
        }
    )
