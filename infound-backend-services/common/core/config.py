import os
from pathlib import Path
from typing import Optional, Dict, Any, List

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# --- 1. 单例状态管理和自定义异常 ---

class InitializationError(Exception):
    """Raised when trying to access settings before they are initialized."""
    pass


# 全局配置实例，默认为 None
_SETTINGS_INSTANCE: Optional['Settings'] = None
# 标记配置是否已成功初始化
_SETTINGS_INITIALIZED: bool = False


# --- 2. 辅助函数（保持不变） ---

def flatten_nested_config(config: Dict[str, Any], parent_key: str = "", separator: str = "__") -> Dict[str, Any]:
    """Flattens nested YAML configuration (e.g., CORS: {ALLOW_ORIGINS: [...]})"""
    flat_config = {}
    for key, value in config.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key
        if isinstance(value, dict) and not isinstance(value, list):
            flat_config.update(flatten_nested_config(value, new_key, separator))
        else:
            flat_config[new_key] = value
    return flat_config


def load_yaml_config(file_path: Path) -> Dict[str, Any]:
    """Loads YAML configuration, handling nested structure."""
    if not file_path.exists():
        return {}  # 配置文件不存在时返回空字典，而不是抛出 FileNotFoundError
    with open(file_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return flatten_nested_config(config)


# --- 3. 配置模型定义（Settings） ---

class Settings(BaseSettings):
    """
    Application settings model, loaded from YAML and environment variables.
    Note: Fields use flattened names (e.g., LOG__LEVEL).
    """
    # --------------------------
    # Global Base Configuration
    # --------------------------
    DEBUG: bool = Field(default=True, validation_alias="DEBUG")
    APP_NAME: str = Field(default="FastAPI Service", validation_alias="APP_NAME")
    # SERVICE_NAME and ENV will be set dynamically in initialize_settings
    SERVICE_NAME: str
    ENV: str
    HOST: str = Field(default="0.0.0.0", validation_alias="HOST")
    API_DOC_PREFIX: str = Field(default="/2025", validation_alias="API_DOC_PREFIX")

    # MySQL Configuration
    MYSQL_HOST: str = Field(default="localhost", validation_alias="MYSQL_HOST")
    MYSQL_PORT: int = Field(default=3306, validation_alias="MYSQL_PORT")
    MYSQL_USER: str = Field(default="root", validation_alias="MYSQL_USER")
    MYSQL_PASSWORD: str = Field(default="", validation_alias="MYSQL_PASSWORD")
    MYSQL_DB: str = Field(default="infound.stg", validation_alias="MYSQL_DB")
    MYSQL_CHARSET: str = Field(default="utf8mb4", validation_alias="MYSQL_CHARSET")

    # Redis Configuration
    # REDIS_URL: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    # REDIS_PASSWORD: Optional[str] = Field(default=None, validation_alias="REDIS_PASSWORD")
    # REDIS_DB: int = Field(default=0, validation_alias="REDIS_DB")

    # Logging Configuration (using flattened names for Pydantic)
    LOG__LEVEL: str = Field(default="INFO", validation_alias="LOG__LEVEL")
    LOG__DIR: str = Field(default="logs", validation_alias="LOG__DIR")
    LOG__FILE_MAX_SIZE: int = Field(default=100, validation_alias="LOG__FILE_MAX_SIZE")
    LOG__FILE_BACKUP_COUNT: int = Field(default=30, validation_alias="LOG__FILE_BACKUP_COUNT")

    # CORS Configuration (using flattened names)
    CORS__ALLOW_ORIGINS: List[str] = Field(default=["*"], validation_alias="CORS__ALLOW_ORIGINS")
    CORS__ALLOW_CREDENTIALS: bool = Field(default=True, validation_alias="CORS__ALLOW_CREDENTIALS")

    # Common Business Configuration
    COMMON_TIMEOUT: int = Field(default=30, validation_alias="COMMON_TIMEOUT")
    MAX_REQUEST_SIZE: int = Field(default=10485760, validation_alias="MAX_REQUEST_SIZE")

    # RabbitMQ Configuration todo
    RABBITMQ_HOST: str = Field(default="", validation_alias="RABBITMQ_HOST")
    RABBITMQ_PORT: int = Field(default=5672, validation_alias="RABBITMQ_PORT")
    RABBITMQ_USER: str = Field(default="", validation_alias="RABBITMQ_USER")
    RABBITMQ_PASSWORD: str = Field(default="", validation_alias="RABBITMQ_PASSWORD")
    RABBITMQ_VHOST: str = Field(default="/", validation_alias="RABBITMQ_VHOST")
    RABBITMQ_EXCHANGE: str = Field(default="", validation_alias="RABBITMQ_EXCHANGE")
    RABBITMQ_QUEUE: str = Field(default="", validation_alias="RABBITMQ_QUEUE")
    RABBITMQ_ROUTING_KEY_PREFIX: str = Field(default="", validation_alias="RABBITMQ_ROUTING_KEY_PREFIX")
    RABBITMQ_OUTREACH_QUEUE: str = Field(default="", validation_alias="RABBITMQ_OUTREACH_QUEUE")
    RABBITMQ_OUTREACH_ROUTING_KEY_PREFIX: str = Field(
        default="",
        validation_alias="RABBITMQ_OUTREACH_ROUTING_KEY_PREFIX",
    )
    RABBITMQ_OUTREACH_QUEUE_PREFIX: str = Field(
        default="",
        validation_alias="RABBITMQ_OUTREACH_QUEUE_PREFIX",
    )
    RABBITMQ_OUTREACH_CONTROL_QUEUE: str = Field(
        default="",
        validation_alias="RABBITMQ_OUTREACH_CONTROL_QUEUE",
    )
    RABBITMQ_OUTREACH_CONTROL_ROUTING_KEY_PREFIX: str = Field(
        default="",
        validation_alias="RABBITMQ_OUTREACH_CONTROL_ROUTING_KEY_PREFIX",
    )
    RABBITMQ_CRAWLER_EXCHANGE: str = Field(
        default="",
        validation_alias="RABBITMQ_CRAWLER_EXCHANGE",
    )
    RABBITMQ_CRAWLER_ROUTING_KEY: str = Field(
        default="",
        validation_alias="RABBITMQ_CRAWLER_ROUTING_KEY",
    )
    RABBITMQ_CRAWLER_QUEUE: str = Field(
        default="",
        validation_alias="RABBITMQ_CRAWLER_QUEUE",
    )

    # SQLAlchemy Asynchronous Connection URL
    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        return (
            f"mysql+aiomysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@"
            f"{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset={self.MYSQL_CHARSET}"
        )

    # Configuration loading rules
    model_config = SettingsConfigDict(
        env_file=None,
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="allow",
        arbitrary_types_allowed=True,
    )

    # Validation example (Uncomment to enable)
    @field_validator("SERVICE_NAME")
    @classmethod
    def service_name_must_be_set(cls, v: str) -> str:
        if not v:
            raise ValueError("SERVICE_NAME cannot be empty.")
        return v


# --- 4. 初始化和获取单例函数 ---

def initialize_settings() -> 'Settings':
    """
    Initializes the global Settings instance. Must be called once at application startup.
    Returns:
        The initialized Settings instance.
    """
    global _SETTINGS_INSTANCE, _SETTINGS_INITIALIZED

    if _SETTINGS_INITIALIZED:
        return _SETTINGS_INSTANCE

    # 1. 确定 ENV 和 SERVICE_NAME 的最终值（CLI > Env Var > Default）
    # 在您的 main.py 中，consumer_arg 就是服务名 (SERVICE_NAME)
    final_env = os.getenv("ENV") or os.getenv("env") or "dev"
    final_service_name = os.getenv("SERVICE_NAME") or os.getenv("service_name")

    if not final_service_name:
        raise ValueError("Service name must be specified via --consumer argument or SERVICE_NAME environment variable.")

    # 2. 定义配置文件路径
    base_yaml_path = Path("configs/base.yaml")
    service_config_dir = Path(f"apps/{final_service_name}/configs")
    service_base_yaml_path = service_config_dir / f"base.yaml"
    service_yaml_path = service_config_dir / f"{final_env}.yaml"

    # 3. 加载并合并配置：基础 → 服务基础 → 服务环境（后面覆盖前面）
    base_config = load_yaml_config(base_yaml_path)
    service_base_config = load_yaml_config(service_base_yaml_path)
    service_config = load_yaml_config(service_yaml_path)

    merged_config = {**base_config, **service_base_config, **service_config, 'SERVICE_NAME': final_service_name,
                     'ENV': final_env}

    # 4. 动态添加 SERVICE_NAME 和 ENV 到配置中
    # Pydantic Settings 需要这些值，即使它们不来自 YAML 或 ENV。

    # 5. 实例化 Settings，Pydantic 会自动处理环境变量覆盖
    try:
        instance = Settings(**merged_config)
    except Exception as e:
        raise InitializationError(f"Failed to validate and instantiate settings: {e}") from e

    # 6. 存储实例并标记初始化完成
    _SETTINGS_INSTANCE = instance
    _SETTINGS_INITIALIZED = True

    return instance


def get_settings() -> 'Settings':
    """
    Retrieves the globally initialized Settings instance.

    Raises:
        InitializationError: If settings have not been initialized.
    """
    if not _SETTINGS_INITIALIZED or _SETTINGS_INSTANCE is None:
        raise InitializationError(
            "Settings have not been initialized. "
            "Call initialize_settings() first at application startup."
        )
    return _SETTINGS_INSTANCE
