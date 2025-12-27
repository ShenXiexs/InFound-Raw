import asyncio
from contextlib import asynccontextmanager
from importlib import import_module

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.core.config import initialize_settings, get_settings
from common.core.exceptions import register_exception_handlers
from common.core.logger import get_logger, initialize_logging
from common.core.response import success_response
from common.core.startup import default_startup_hook, default_shutdown_hook

initialize_settings()
settings = get_settings()

initialize_logging()
logger = get_logger()


# Dynamically import service router and hooks
def import_service_components(service_name: str):
    """
    Dynamically import three service components:
    1. router
    2. startup hook
    3. shutdown hook
    """
    try:
        # Import router (apps.<service>.apis.router)
        router_module = import_module(f"apps.{service_name}.apis.router")
        router = getattr(router_module, f"open_api_router")

        # Import service-specific hooks (fallback to defaults)
        try:
            startup_module = import_module(f"apps.{service_name}.startup")
            # Middleware registration function (optional)
            register_middlewares = getattr(startup_module, "register_middlewares", None)
            startup_hook = getattr(startup_module, "startup_hook")
            shutdown_hook = getattr(startup_module, "shutdown_hook")
        except (ImportError, AttributeError):
            logger.warning(f"Service {service_name} has no custom hooks; using defaults")
            register_middlewares = None
            startup_hook = default_startup_hook
            shutdown_hook = default_shutdown_hook

        return router, register_middlewares, startup_hook, shutdown_hook
    except (ImportError, AttributeError) as e:
        logger.error(f"Failed to import components for service {service_name}", exc_info=True)
        raise ValueError(f"Service {service_name} configuration error: {str(e)}") from e


def create_app() -> FastAPI:
    """Create FastAPI app with shared + service-specific wiring."""
    logger.info(f"Starting service {settings.SERVICE_NAME} (env={settings.ENV})")

    # 1. Import service components (router + hooks)
    service_router, service_register_middlewares, service_startup_hook, service_shutdown_hook = import_service_components(
        settings.SERVICE_NAME)

    # 2. Lifespan hooks
    @asynccontextmanager
    async def lifespan(app_local: FastAPI):
        # Run service startup hook
        if asyncio.iscoroutinefunction(service_startup_hook):
            await service_startup_hook(app_local)
        else:
            service_startup_hook(app_local)
        yield
        # Run service shutdown hook
        if asyncio.iscoroutinefunction(service_shutdown_hook):
            await service_shutdown_hook(app_local)
        else:
            service_shutdown_hook(app_local)

    # 3. Core app setup (shared)
    app_temp = FastAPI(
        title=settings.APP_NAME,
        description=f"{settings.APP_NAME} - service: {settings.SERVICE_NAME} - env: {settings.ENV}",
        version="1.0.0",
        docs_url=f"{settings.API_DOC_PREFIX}/docs" if settings.DEBUG else None,
        redoc_url=f"{settings.API_DOC_PREFIX}/redoc" if settings.DEBUG else None,
        lifespan=lifespan
    )
    app_temp.state.debug = settings.DEBUG

    # 4. CORS middleware
    if settings.DEBUG:
        app_temp.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # CORS config
        app_temp.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ALLOW_ORIGINS,
            allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    if service_register_middlewares:
        service_register_middlewares(app_temp)

    # 5. Register exception handlers
    register_exception_handlers(app_temp)

    # 6. Register service router
    app_temp.include_router(service_router)

    return app_temp


app = create_app()


@app.get(f"/health")
async def health_check():
    return success_response({"status": "healthy", "service_name": settings.SERVICE_NAME, "env": settings.ENV})
