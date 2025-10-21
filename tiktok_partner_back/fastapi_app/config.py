"""
FastAPI 应用配置
"""
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """应用配置"""

    # 应用基本信息
    APP_NAME: str = "TikTok Partner Management System"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = True

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # JWT 认证配置
    SECRET_KEY: str = "your-secret-key-change-this-in-production-2024"  # 生产环境务必修改！
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7天

    # 数据库配置
    DATABASE_URL: str = "sqlite:///./data/record/system.db"

    # 原有爬虫系统的数据库
    CRAWLER_DB_PATH: str = "data/record/central_record.db"

    # 账号池配置
    ACCOUNT_POOL_CONFIG: str = "config/accounts.json"

    # 任务管理器配置
    MAX_WORKERS: int = 3

    # CORS 配置
    CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        # 添加你的前端域名
    ]

    # 日志配置
    LOG_DIR: str = "logs/fastapi"

    class Config:
        env_file = ".env"
        case_sensitive = True


# 全局配置实例
settings = Settings()


# 确保必要的目录存在
def ensure_directories():
    """确保必要的目录存在"""
    dirs = [
        Path("data/record"),
        Path("logs/fastapi"),
        Path("config"),
        Path("data/tasks"),
    ]
    for dir_path in dirs:
        dir_path.mkdir(parents=True, exist_ok=True)


ensure_directories()
