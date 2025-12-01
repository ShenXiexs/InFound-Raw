"""
FastAPI application entrypoint.
"""
import argparse
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.v1 import auth, crawler, chat, product, sample, accounts, card
from core.config import settings
from utils.response import create_response

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/api/app.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management for startup/shutdown hooks."""
    logger.info("FastAPI application booting | env=%s | port=%s", settings.ENVIRONMENT, settings.PORT)
    yield
    logger.info("FastAPI application shutdown complete")

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="TikTok Partner backend API",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content=create_response(success=False, message=f"Internal server error: {str(exc)}")
    )

# Health checks
@app.get("/")
async def root():
    return create_response(
        success=True,
        message="TikTok Partner API is running",
        data={"version": settings.VERSION}
    )

@app.get("/health")
async def health_check():
    return create_response(success=True, message="healthy")

# Register routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(crawler.router, prefix="/api/v1/crawler", tags=["Crawler"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(product.router, prefix="/api/v1/product", tags=["Product"])
app.include_router(sample.router, prefix="/api/v1/sample", tags=["Sample"])
app.include_router(accounts.router, prefix="/api/v1/accounts", tags=["Accounts"])
app.include_router(card.router, prefix="/api/v1/card", tags=["Card"])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run TikTok Partner FastAPI service.")
    parser.add_argument("--host", default=settings.HOST, help="Host interface (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=settings.PORT, help="Port (default 8000)")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable development auto-reload (do not use in production).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of Uvicorn workers (default 1, aligned with systemd units).",
    )
    args = parser.parse_args()

    os.environ.setdefault("UVICORN_NO_UVLOOP", "1")
    reload_dirs = [
        "api",
        "core",
        "schemas",
        "services",
        "crawler",
        "models",
        "utils",
        "chat_history",
        "product_card",
        "manage_sample",
    ]
    reload_excludes = ["data/*", "logs/*", "task/*", "task_json/*"]
    enable_reload = args.reload and settings.DEBUG

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=enable_reload,
        workers=args.workers,
        loop="asyncio",
        http="h11",
        reload_dirs=[str(Path(dir_path)) for dir_path in reload_dirs] if enable_reload else None,
        reload_excludes=reload_excludes if enable_reload else None,
    )
