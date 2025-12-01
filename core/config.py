"""
Application configuration management powered by Pydantic settings.
"""
from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    """Application configuration container."""
    
    # General settings
    PROJECT_NAME: str = "TikTok Partner API"
    VERSION: str = "1.0.0"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    ENVIRONMENT: str = os.getenv("APP_ENV", "production")
    
    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production-please-make-it-long-and-random"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
    ]
    
    # Database
    DB_PATH: str = "data/record/central_record.db"
    
    # Account pool configuration
    ACCOUNT_CONFIG_PATH: str = "config/accounts.json"
    
    # API user config file
    USERS_CONFIG_PATH: str = "config/users.json"
    
    # Task configuration
    TASK_DIR: str = "task"  # Legacy compatibility
    TASK_DATA_DIR: str = "data/tasks"
    MAX_WORKERS: int = 3
    MAX_CONCURRENT_TASKS: int = 1
    TASK_TIMEOUT_MINUTES: int = 90
    
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()
