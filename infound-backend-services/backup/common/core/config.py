import os
from pathlib import Path
from threading import Lock
from typing import Optional, Dict, Any

from pydantic import Field, field_validator, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from ruamel.yaml import YAML

yaml = YAML(typ="safe")

# --- 常量 ---
ENV_NESTED_DELIMITER = "__"
CONFIG_BASE_DIR = Path(os.getenv("CONFIG_BASE_DIR", "."))

_SETTINGS_INSTANCE: Optional['Settings'] = None
_SETTINGS_INITIALIZED: bool = False
_SETTINGS_LOCK = Lock()


class InitializationError(Exception):
    pass


# --- 子模型：改用 BaseModel (更轻量) ---

class MySQLSettings(BaseModel):
    host: str = "47.238.5.253"
    port: int = 8801
    user: str = "infound-stg"
    password: str = "&3$BSW)mGxE(Zk"
    db: str = "infound.stg"
    charset: str = "utf8mb4"

    @property
    def sqlalchemy_database_url(self) -> str:
        return f"mysql+aiomysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}?charset={self.charset}"


class RedisSettings(BaseModel):
    host: str = "47.238.5.253"
    port: int = 8802
    password: str = "gcc+tvKgtjd&n_^@"
    db: int = 0
    prefix: str = "if.dev"


class LogSettings(BaseModel):
    level: str = "INFO"
    dir: str = "logs"
    file_max_size: int = 10
    file_backup_count: int = 30


class RabbitMQSettings(BaseModel):
    # 依然可以使用 validation_alias 处理特殊的环境变量冲突
    host: str = Field("47.238.5.253", validation_alias="RABBITMQ__HOST")
    port: int = Field(8803, validation_alias="RABBITMQ__PORT")
    username: str = Field("infound.stg", validation_alias="RABBITMQ__USERNAME")
    password: str = Field("xy6Ucz5IZ@Z%P)", validation_alias="RABBITMQ__PASSWORD")
    vhost: str = "/infound.stg"
    prefetch_count: int = 1
    reconnect_delay: int = 5
    max_reconnect_attempts: int = 4

    exchange_name: str = "crawler.direct"
    queue_name: str = "crawler.tiktok.sample.queue"
    routing_key_prefix: str = "crawler.tiktok.sample.key"

    outreach_queue: str = "chatbot.outreach.queue.topic"
    outreach_routing_key_prefix: str = "chatbot.outreach"
    outreach_queue_prefix: str = "chatbot.outreach.queue"
    outreach_control_queue: str = "chatbot.outreach.control.queue"
    outreach_control_routing_key_prefix: str = "chatbot.outreach.control"

    crawler_exchange: str = "crawler.direct"
    crawler_routing_key: str = "crawler.tiktok.creator.key"
    crawler_queue: str = "crawler.tiktok.creator.queue"


class ChatBotScheduleSettings(BaseModel):
    publisher_enabled: bool = True
    poll_interval_seconds: int = 15
    batch_size: int = 20
    supported_region: str = "MX"


# --- 核心配置模型 ---

class Settings(BaseSettings):
    app_name: str = "INFound Backend Service"
    env: str = "dev"
    debug: bool = True
    service_name: str

    # 嵌套子配置：由 Pydantic 自动处理字典嵌套
    mysql: MySQLSettings = Field(default_factory=MySQLSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    log: LogSettings = Field(default_factory=LogSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    # chat_bot_schedule: Optional[ChatBotScheduleSettings] = Field(default=None)

    model_config = SettingsConfigDict(
        env_nested_delimiter=ENV_NESTED_DELIMITER,
        case_sensitive=False,
        extra="allow"  # 建议 ignore，避免 YAML 中无关 key 导致报错
    )

    @field_validator("service_name")
    @classmethod
    def service_name_must_be_set(cls, v: str) -> str:
        if not v: raise ValueError("service_name cannot be empty")
        return v


# --- 工具函数 ---

def _deep_merge(base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    """深度合并字典，用于处理多层 YAML 嵌套覆盖"""
    for k, v in update.items():
        if isinstance(v, dict) and k in base and isinstance(base[k], dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _load_yaml_config(file_path: Path) -> Dict[str, Any]:
    if not file_path.exists(): return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.load(f) or {}
    except Exception as e:
        raise InitializationError(f"YAML加载失败: {file_path} - {e}")


# --- 初始化 ---

def initialize_settings(env_arg: Optional[str] = None, consumer_arg: Optional[str] = None) -> Settings:
    global _SETTINGS_INSTANCE, _SETTINGS_INITIALIZED

    if _SETTINGS_INITIALIZED:
        return _SETTINGS_INSTANCE

    with _SETTINGS_LOCK:
        if _SETTINGS_INITIALIZED:
            return _SETTINGS_INSTANCE

        try:
            # 1. 确定核心参数
            final_env = env_arg or os.getenv("ENV") or "dev"
            final_service_name = consumer_arg or os.getenv("SERVICE_NAME")

            if not final_service_name:
                raise InitializationError("SERVICE_NAME 缺失")

            # 2. 路径定位
            base_yaml = CONFIG_BASE_DIR / "configs" / "base.yaml"
            svc_base_yaml = CONFIG_BASE_DIR / "apps" / final_service_name / "configs" / "base.yaml"
            svc_env_yaml = CONFIG_BASE_DIR / "apps" / final_service_name / "configs" / f"{final_env}.yaml"

            # 3. 加载并深度合并 (不进行扁平化)
            config_data = {}
            for path in [base_yaml, svc_base_yaml, svc_env_yaml]:
                _deep_merge(config_data, _load_yaml_config(path))

            # 4. 强制注入
            config_data.update({"env": final_env, "service_name": final_service_name})

            # 5. 实例化：使用构造器以启用环境变量覆盖逻辑
            _SETTINGS_INSTANCE = Settings(**config_data)
            _SETTINGS_INITIALIZED = True
            return _SETTINGS_INSTANCE

        except Exception as e:
            raise InitializationError(f"配置实例化失败: {e}")


def get_settings() -> Settings:
    """
    负责【读】：在业务代码（Controller, Service, Dao）中调用。
    """
    if not _SETTINGS_INITIALIZED or _SETTINGS_INSTANCE is None:
        # 这里的报错是为了提醒开发者：你忘记在 main.py 初始化了
        raise InitializationError(
            "Settings 尚未初始化。请确保在应用启动入口（如 main.py）先调用 initialize_settings()。"
        )
    return _SETTINGS_INSTANCE
