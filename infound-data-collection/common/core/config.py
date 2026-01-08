import os
from pathlib import Path
from typing import Optional, Dict, Any, List

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ----------------------------------------------------------------------
# 1. 内部单例存储和状态
# ----------------------------------------------------------------------

# 私有的配置实例存储变量
_SETTINGS_INSTANCE: Optional['Settings'] = None
# 标记是否已初始化
_SETTINGS_INITIALIZED: bool = False


class InitializationError(Exception):
    """配置初始化错误"""
    pass


# ----------------------------------------------------------------------
# 2. 配置模型定义
# ----------------------------------------------------------------------

class Settings(BaseSettings):
    # --------------------------
    # 全局基础配置（所有服务共用）
    # --------------------------
    DEBUG: bool = Field(default=True, validation_alias="DEBUG")
    APP_NAME: str = Field(default="MQ Consumer Service", validation_alias="APP_NAME")
    CONSUMER: str = Field(default="", validation_alias="CONSUMER")
    ENV: str = Field(default="dev", validation_alias="ENV")

    # MySQL 基础配置
    MYSQL_HOST: str = Field(default="localhost", validation_alias="MYSQL_HOST")
    MYSQL_PORT: int = Field(default=3306, validation_alias="MYSQL_PORT")
    MYSQL_USER: str = Field(default="root", validation_alias="MYSQL_USER")
    MYSQL_PASSWORD: str = Field(default="", validation_alias="MYSQL_PASSWORD")
    MYSQL_DB: str = Field(default="fastapi_db", validation_alias="MYSQL_DB")
    MYSQL_CHARSET: str = Field(default="utf8mb4", validation_alias="MYSQL_CHARSET")

    # Redis 基础配置
    REDIS_URL: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    REDIS_PASSWORD: Optional[str] = Field(default=None, validation_alias="REDIS_PASSWORD")
    REDIS_DB: int = Field(default=0, validation_alias="REDIS_DB")

    # 日志基础配置
    LOG_LEVEL: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    LOG_DIR: str = Field(default="logs", validation_alias="LOG_DIR")
    LOG_FILE_MAX_SIZE: int = Field(default=100, validation_alias="LOG_FILE_MAX_SIZE")
    LOG_FILE_BACKUP_COUNT: int = Field(default=30, validation_alias="LOG_FILE_BACKUP_COUNT")

    # CONSUMERS 配置
    CONSUMERS: List[str] = Field(default=["*"], validation_alias="CONSUMERS")

    RABBITMQ_HOST: str = Field(default="localhost", validation_alias="RABBITMQ__HOST")
    RABBITMQ_PORT: int = Field(default=5672, validation_alias="RABBITMQ__PORT")
    RABBITMQ_USERNAME: str = Field(default="guest", validation_alias="RABBITMQ__USERNAME")
    RABBITMQ_PASSWORD: str = Field(default="guest", validation_alias="RABBITMQ__PASSWORD")
    RABBITMQ_VHOST: str = Field(default="/", validation_alias="RABBITMQ__VHOST")
    RABBITMQ_EXCHANGE_NAME: str = Field(default="mq_consumer_queue", validation_alias="RABBITMQ__EXCHANGE_NAME")
    RABBITMQ_ROUTING_KEY: str = Field(default="mq_consumer_queue", validation_alias="RABBITMQ__ROUTING_KEY")
    RABBITMQ_QUEUE_NAME: str = Field(default="mq_consumer_queue", validation_alias="RABBITMQ__QUEUE_NAME")
    RABBITMQ_PREFETCH_COUNT: int = Field(default=1, validation_alias="RABBITMQ__PREFETCH_COUNT")
    RABBITMQ_RECONNECT_DELAY: int = Field(default=5, validation_alias="RABBITMQ__RECONNECT_DELAY")
    RABBITMQ_MAX_RECONNECT_ATTEMPTS: int = Field(default=5, validation_alias="RABBITMQ__MAX_RECONNECT_ATTEMPTS")
    # At-most-once delivery: consume+ack immediately (no retry on crash/kill).
    RABBITMQ_AT_MOST_ONCE: bool = Field(default=False, validation_alias="RABBITMQ__AT_MOST_ONCE")

    # Optional: unified chatbot queue overrides
    RABBITMQ_SAMPLE_EXCHANGE_NAME: Optional[str] = Field(
        default=None, validation_alias="RABBITMQ_SAMPLE_EXCHANGE_NAME"
    )
    RABBITMQ_SAMPLE_ROUTING_KEY: Optional[str] = Field(
        default=None, validation_alias="RABBITMQ_SAMPLE_ROUTING_KEY"
    )
    RABBITMQ_SAMPLE_QUEUE_NAME: Optional[str] = Field(
        default=None, validation_alias="RABBITMQ_SAMPLE_QUEUE_NAME"
    )
    RABBITMQ_SAMPLE_PREFETCH_COUNT: Optional[int] = Field(
        default=None, validation_alias="RABBITMQ_SAMPLE_PREFETCH_COUNT"
    )
    RABBITMQ_SAMPLE_AT_MOST_ONCE: Optional[bool] = Field(
        default=None, validation_alias="RABBITMQ_SAMPLE_AT_MOST_ONCE"
    )
    RABBITMQ_OUTREACH_EXCHANGE_NAME: Optional[str] = Field(
        default=None, validation_alias="RABBITMQ_OUTREACH_EXCHANGE_NAME"
    )
    RABBITMQ_OUTREACH_ROUTING_KEY: Optional[str] = Field(
        default=None, validation_alias="RABBITMQ_OUTREACH_ROUTING_KEY"
    )
    RABBITMQ_OUTREACH_QUEUE_NAME: Optional[str] = Field(
        default=None, validation_alias="RABBITMQ_OUTREACH_QUEUE_NAME"
    )
    RABBITMQ_OUTREACH_QUEUE_PREFIX: Optional[str] = Field(
        default=None, validation_alias="RABBITMQ_OUTREACH_QUEUE_PREFIX"
    )
    RABBITMQ_OUTREACH_PREFETCH_COUNT: Optional[int] = Field(
        default=None, validation_alias="RABBITMQ_OUTREACH_PREFETCH_COUNT"
    )
    RABBITMQ_OUTREACH_AT_MOST_ONCE: Optional[bool] = Field(
        default=None, validation_alias="RABBITMQ_OUTREACH_AT_MOST_ONCE"
    )
    RABBITMQ_OUTREACH_CONTROL_EXCHANGE_NAME: Optional[str] = Field(
        default=None, validation_alias="RABBITMQ_OUTREACH_CONTROL_EXCHANGE_NAME"
    )
    RABBITMQ_OUTREACH_CONTROL_ROUTING_KEY: Optional[str] = Field(
        default=None, validation_alias="RABBITMQ_OUTREACH_CONTROL_ROUTING_KEY"
    )
    RABBITMQ_OUTREACH_CONTROL_QUEUE_NAME: Optional[str] = Field(
        default=None, validation_alias="RABBITMQ_OUTREACH_CONTROL_QUEUE_NAME"
    )
    RABBITMQ_OUTREACH_CONTROL_PREFETCH_COUNT: Optional[int] = Field(
        default=None, validation_alias="RABBITMQ_OUTREACH_CONTROL_PREFETCH_COUNT"
    )
    RABBITMQ_OUTREACH_CONTROL_AT_MOST_ONCE: Optional[bool] = Field(
        default=None, validation_alias="RABBITMQ_OUTREACH_CONTROL_AT_MOST_ONCE"
    )

    # Optional: dual-queue setup (completed vs other) within a single process.
    RABBITMQ_COMPLETED_ROUTING_KEY: str = Field(
        default="mq_consumer_queue.completed",
        validation_alias="RABBITMQ__COMPLETED__ROUTING_KEY",
    )
    RABBITMQ_COMPLETED_QUEUE_NAME: str = Field(
        default="mq_consumer_queue.completed",
        validation_alias="RABBITMQ__COMPLETED__QUEUE_NAME",
    )
    RABBITMQ_OTHER_ROUTING_KEY: str = Field(
        default="mq_consumer_queue.other",
        validation_alias="RABBITMQ__OTHER__ROUTING_KEY",
    )
    RABBITMQ_OTHER_QUEUE_NAME: str = Field(
        default="mq_consumer_queue.other",
        validation_alias="RABBITMQ__OTHER__QUEUE_NAME",
    )

    INNER_API_BASE_URL: str = Field(
        default="http://127.0.0.1:8000",
        validation_alias="INNER_API__BASE_URL",
    )
    INNER_API_SAMPLE_PATH: str = Field(
        default="/samples/ingest",
        validation_alias="INNER_API__SAMPLE_PATH",
    )
    INNER_API_CREATOR_PATH: str = Field(
        default="/creators/ingest",
        validation_alias="INNER_API__CREATOR_PATH",
    )
    INNER_API_OUTREACH_TASK_PATH: str = Field(
        default="/outreach_tasks/ingest",
        validation_alias="INNER_API__OUTREACH_TASK_PATH",
    )
    INNER_API_CHATBOT_PATH: str = Field(
        default="/chatbot/messages",
        validation_alias="INNER_API__CHATBOT_PATH",
    )
    INNER_API_OUTREACH_CHATBOT_PATH: str = Field(
        default="/chatbot/outreach/messages",
        validation_alias="INNER_API__OUTREACH_CHATBOT_PATH",
    )
    INNER_API_OUTREACH_CONTROL_PATH: str = Field(
        default="/chatbot/outreach/control",
        validation_alias="INNER_API__OUTREACH_CONTROL_PATH",
    )
    INNER_API_CREATOR_HISTORY_PATH: str = Field(
        default="/creators/history",
        validation_alias="INNER_API__CREATOR_HISTORY_PATH",
    )
    INNER_API_OUTREACH_PROGRESS_PATH: str = Field(
        default="/outreach_tasks/progress",
        validation_alias="INNER_API__OUTREACH_PROGRESS_PATH",
    )
    INNER_API_TIMEOUT: int = Field(
        default=30,
        validation_alias="INNER_API__TIMEOUT",
    )
    INNER_API_AUTH_REQUIRED_HEADER: str = Field(
        default="X-INFound-Inner-Service-Token",
        validation_alias="INNER_API_AUTH__REQUIRED_HEADER",
    )
    INNER_API_AUTH_VALID_TOKENS: List[str] = Field(
        default_factory=list,
        validation_alias="INNER_API_AUTH__VALID_TOKENS",
    )
    INNER_API_AUTH_TOKEN: Optional[str] = Field(
        default=None,
        validation_alias="INNER_API_AUTH__TOKEN",
    )

    OUTREACH_CHATBOT_WORKER_COUNT: int = Field(
        default=2,
        validation_alias="OUTREACH_CHATBOT_WORKER_COUNT",
    )
    SAMPLE_MANUAL_EMAIL_CODE_INPUT: bool = Field(
        default=False,
        validation_alias="SAMPLE_MANUAL_EMAIL_CODE_INPUT",
    )
    SAMPLE_MANUAL_EMAIL_CODE_INPUT_TIMEOUT_SECONDS: int = Field(
        default=180,
        validation_alias="SAMPLE_MANUAL_EMAIL_CODE_INPUT_TIMEOUT_SECONDS",
    )
    CHATBOT_MANUAL_LOGIN: bool = Field(
        default=False,
        validation_alias="CHATBOT_MANUAL_LOGIN",
    )
    CHATBOT_MANUAL_EMAIL_CODE_INPUT: bool = Field(
        default=False,
        validation_alias="CHATBOT_MANUAL_EMAIL_CODE_INPUT",
    )
    CHATBOT_MANUAL_EMAIL_CODE_INPUT_TIMEOUT_SECONDS: int = Field(
        default=180,
        validation_alias="CHATBOT_MANUAL_EMAIL_CODE_INPUT_TIMEOUT_SECONDS",
    )

    # --------------------------
    # 计算属性 (使用 @property 替代，它们不会被 YAML 或环境变量覆盖)
    # --------------------------
    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        # 使用扁平化后的字段名进行拼接
        return (
            f"mysql+asyncmy://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@"
            f"{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset={self.MYSQL_CHARSET}"
        )

    @property
    def SQLALCHEMY_SYNC_DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@"
            f"{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset={self.MYSQL_CHARSET}"
        )

    # --------------------------
    # Pydantic 配置规则
    # --------------------------
    model_config = SettingsConfigDict(
        # env_prefix: 保持为空，以便匹配所有大写环境变量
        env_prefix='',
        # 环境变量嵌套分隔符，与 YAML 扁平化规则保持一致
        env_nested_delimiter="__",
        case_sensitive=True,  # 字段名区分大小写，必须与模型中的大写字段名完全匹配
        extra="allow",  # 忽略 YAML 或环境变量中存在但模型中未定义的键
        arbitrary_types_allowed=True,
    )


# ----------------------------------------------------------------------
# 3. 初始化工具函数 (封装 YAML 加载和扁平化逻辑)
# ----------------------------------------------------------------------

def _flatten_nested_config(config: Dict[str, Any], parent_key: str = "", separator: str = "__") -> Dict[str, Any]:
    """扁平化嵌套 YAML 配置，并转换为大写键名以匹配 Pydantic 字段"""
    flat_config = {}
    for key, value in config.items():
        # 转换为大写，并使用 __ 作为分隔符
        new_key = f"{parent_key}{separator}{key.upper()}" if parent_key else key.upper()

        if isinstance(value, dict) and not isinstance(value, list):
            # 递归处理嵌套字典
            flat_config.update(_flatten_nested_config(value, new_key, separator))
        else:
            flat_config[new_key] = value

    return flat_config


def _load_yaml_config(file_path: Path) -> Dict[str, Any]:
    """加载 YAML 配置，如果文件不存在则返回空字典"""
    if not file_path.exists():
        print(f"配置警告: 配置文件不存在，跳过加载：{file_path}")
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return config


def initialize_settings(env_arg: Optional[str] = None, consumer_arg: Optional[str] = None):
    """
    初始化并设置全局单例配置实例。在应用启动时调用一次。

    Args:
        env_arg: 命令行传入的环境名 (如 'stg', 'pro')，将覆盖 ENV 环境变量。
        consumer_arg: 命令行传入的服务名/消费端标识 (如 'api_v1')，将覆盖 SERVICE_NAME 环境变量。
    """
    global _SETTINGS_INSTANCE, _SETTINGS_INITIALIZED

    if _SETTINGS_INITIALIZED:
        raise InitializationError("配置已初始化，请勿重复调用 initialize_settings()")

    # 1. 基础变量获取 (优先级：函数参数 > 环境变量 > 默认值)
    # ENV：CLI/函数参数优先，其次是环境变量，最后是默认值 'dev'
    env = (env_arg or os.getenv("ENV", "dev")).lower()

    # CONSUMER (即 service_name 标识)：CLI/函数参数优先，其次是环境变量 CONSUMER
    consumer = consumer_arg or os.getenv("CONSUMER")

    if not consumer:
        # 错误信息已更新为 CONSUMER
        raise ValueError("必须通过 CLI 参数或 CONSUMER 环境变量指定服务名（如 api_v1、api_v2）")

    # 2. 配置文件路径定义
    # 查找顺序：全局基础 -> 服务基础 -> 服务环境
    base_yaml_path = Path("configs/base.yaml")
    service_config_dir = Path(f"apps/{consumer}/configs")
    service_base_yaml_path = service_config_dir / f"base.yaml"
    service_yaml_path = service_config_dir / f"{env}.yaml"

    print(f"正在加载配置文件：\n{service_base_yaml_path}\n{service_yaml_path}")

    # 3. 加载并合并 YAML 配置
    merged_yaml_config = {}
    yaml_config_sources = [
        _load_yaml_config(base_yaml_path),
        _load_yaml_config(service_base_yaml_path),
        _load_yaml_config(service_yaml_path)
    ]

    for config_source in yaml_config_sources:
        if config_source:
            # 扁平化并覆盖
            merged_yaml_config.update(_flatten_nested_config(config_source))

    # 4. 组装初始数据 (传入 ENV 和 SERVICE_NAME)
    # 注意：SERVICE_NAME 是 Pydantic 字段，这里将 consumer 的值赋给 SERVICE_NAME
    initial_data = {
        "ENV": env,  # 存储为大写
        "CONSUMER": consumer,
        **merged_yaml_config
    }

    # 5. 使用 Pydantic 进行配置验证和加载 (自动处理环境变量覆盖)
    try:
        # 使用 model_validate 实例化，它会先处理传入的 initial_data，然后检查环境变量覆盖
        _SETTINGS_INSTANCE = Settings.model_validate(initial_data)
        _SETTINGS_INITIALIZED = True
    except Exception as e:
        # 捕获所有 Pydantic 验证错误
        raise InitializationError(f"Pydantic 配置验证失败: {e}")


# ----------------------------------------------------------------------
# 4. 单例访问函数
# ----------------------------------------------------------------------

def get_settings() -> 'Settings':
    """
    获取全局单例配置实例。
    项目中的任何位置都可以通过导入此函数来获取配置。
    """
    global _SETTINGS_INSTANCE
    if _SETTINGS_INSTANCE is None:
        raise InitializationError("配置尚未初始化。请确保在应用启动时调用 initialize_settings()。")
    return _SETTINGS_INSTANCE
