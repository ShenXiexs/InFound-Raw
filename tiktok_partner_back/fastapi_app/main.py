"""
FastAPI 主应用入口
TikTok Partner Management System
"""
import multiprocessing as mp
mp.set_start_method('fork', force=True)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from datetime import datetime
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .config import settings
from .database import init_db
from .routers import auth_router, tasks_router, accounts_router


# 配置日志
log_dir = Path(settings.LOG_DIR)
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format='[FastAPI] %(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / f"{datetime.now():%Y%m%d}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# 应用生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的操作"""
    # 启动时
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info("=" * 60)
    logger.info("初始化数据库...")
    init_db()
    logger.info("✓ 数据库初始化完成")
    logger.info(f"📡 服务器地址: http://{settings.HOST}:{settings.PORT}")
    logger.info(f"📚 API 文档: http://{settings.HOST}:{settings.PORT}/docs")
    logger.info(f"📋 ReDoc 文档: http://{settings.HOST}:{settings.PORT}/redoc")
    logger.info("=" * 60)

    yield

    # 关闭时
    logger.info("应用正在关闭...")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    ## TikTok Shop 合作伙伴管理系统

    这是一个基于 FastAPI 的 TikTok Shop 创作者爬虫管理系统。

    ### 功能特性
    - 🔐 **用户认证系统**: JWT Token 认证，安全可靠
    - 📊 **任务管理**: 提交、查询、取消爬虫任务
    - 👥 **账号池管理**: 管理多个 TikTok Shop 账号
    - 🌍 **多区域支持**: 支持 FR、MX 等多个区域
    - 📈 **并行处理**: 多进程并行执行爬虫任务

    ### 认证说明
    大部分 API 需要登录后才能访问。请先注册账号，然后登录获取 access_token。

    在 Swagger UI 中点击右上角的 🔒 Authorize 按钮，输入 token 即可测试受保护的 API。
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    debug=settings.DEBUG,
)


# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    logger.error(f"全局异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "服务器内部错误",
            "detail": str(exc) if settings.DEBUG else "请联系管理员",
        }
    )


# 注册路由
app.include_router(auth_router)
app.include_router(tasks_router)
app.include_router(accounts_router)


# 健康检查
@app.get("/", tags=["系统"])
async def root():
    """根路径 - 系统信息"""
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/api/health", tags=["系统"])
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


# 开发环境启动
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if settings.DEBUG else "warning",
    )
