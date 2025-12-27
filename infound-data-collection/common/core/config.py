import os
from pathlib import Path
from typing import Optional, Dict, Any, List

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ----------------------------------------------------------------------
# 1. Internal singleton state
# ----------------------------------------------------------------------

# Private settings instance storage
_SETTINGS_INSTANCE: Optional['Settings'] = None
# Whether initialization has completed
_SETTINGS_INITIALIZED: bool = False


class InitializationError(Exception):
    """Settings initialization error."""
    pass


# ----------------------------------------------------------------------
# 2. Settings model
# ----------------------------------------------------------------------

class Settings(BaseSettings):
    # --------------------------
    # Global base config (shared by all services)
    # --------------------------
    DEBUG: bool = Field(default=True, validation_alias="DEBUG")
    APP_NAME: str = Field(default="MQ Consumer Service", validation_alias="APP_NAME")
    CONSUMER: str = Field(default="", validation_alias="CONSUMER")
    ENV: str = Field(default="dev", validation_alias="ENV")

    # MySQL base config
    MYSQL_HOST: str = Field(default="localhost", validation_alias="MYSQL_HOST")
    MYSQL_PORT: int = Field(default=3306, validation_alias="MYSQL_PORT")
    MYSQL_USER: str = Field(default="root", validation_alias="MYSQL_USER")
    MYSQL_PASSWORD: str = Field(default="", validation_alias="MYSQL_PASSWORD")
    MYSQL_DB: str = Field(default="fastapi_db", validation_alias="MYSQL_DB")
    MYSQL_CHARSET: str = Field(default="utf8mb4", validation_alias="MYSQL_CHARSET")

    # Redis base config
    REDIS_URL: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    REDIS_PASSWORD: Optional[str] = Field(default=None, validation_alias="REDIS_PASSWORD")
    REDIS_DB: int = Field(default=0, validation_alias="REDIS_DB")

    # Logging base config
    LOG_LEVEL: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    LOG_DIR: str = Field(default="logs", validation_alias="LOG_DIR")
    LOG_FILE_MAX_SIZE: int = Field(default=100, validation_alias="LOG_FILE_MAX_SIZE")
    LOG_FILE_BACKUP_COUNT: int = Field(default=30, validation_alias="LOG_FILE_BACKUP_COUNT")

    # Consumers list
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

    # --------------------------
    # Computed properties (@property values are not overridden by YAML/env)
    # --------------------------
    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        # Compose using flattened field names
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
    # Pydantic config
    # --------------------------
    model_config = SettingsConfigDict(
        # env_prefix is empty to match uppercase env vars
        env_prefix='',
        # Nested delimiter matches YAML flattening
        env_nested_delimiter="__",
        case_sensitive=True,  # field names are case-sensitive
        extra="allow",  # ignore keys not defined in the model
        arbitrary_types_allowed=True,
    )


# ----------------------------------------------------------------------
# 3. Initialization helpers (YAML loading + flattening)
# ----------------------------------------------------------------------

def _flatten_nested_config(config: Dict[str, Any], parent_key: str = "", separator: str = "__") -> Dict[str, Any]:
    """Flatten nested YAML config and upper-case keys for Pydantic."""
    flat_config = {}
    for key, value in config.items():
        # Upper-case keys and join with the delimiter
        new_key = f"{parent_key}{separator}{key.upper()}" if parent_key else key.upper()

        if isinstance(value, dict) and not isinstance(value, list):
            # Recurse into nested dicts
            flat_config.update(_flatten_nested_config(value, new_key, separator))
        else:
            flat_config[new_key] = value

    return flat_config


def _load_yaml_config(file_path: Path) -> Dict[str, Any]:
    """Load YAML config; return empty dict when file is missing."""
    if not file_path.exists():
        print(f"Config warning: file not found, skipping: {file_path}")
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    return config


def initialize_settings(env_arg: Optional[str] = None, consumer_arg: Optional[str] = None):
    """
    Initialize and store the global settings instance (call once at startup).

    Args:
        env_arg: CLI env name (e.g., 'stg', 'pro'); overrides ENV.
        consumer_arg: CLI consumer name (e.g., 'api_v1'); overrides CONSUMER.
    """
    global _SETTINGS_INSTANCE, _SETTINGS_INITIALIZED

    if _SETTINGS_INITIALIZED:
        raise InitializationError("Settings already initialized; do not call initialize_settings() twice.")

    # 1. Base values (priority: args > env vars > defaults)
    env = (env_arg or os.getenv("ENV", "dev")).lower()

    # CONSUMER (service identifier)
    consumer = consumer_arg or os.getenv("CONSUMER")

    if not consumer:
        raise ValueError("CONSUMER must be provided via CLI or environment (e.g., api_v1, api_v2).")

    # 2. Config file paths (base -> service base -> service env)
    base_yaml_path = Path("configs/base.yaml")
    service_config_dir = Path(f"apps/{consumer}/configs")
    service_base_yaml_path = service_config_dir / f"base.yaml"
    service_yaml_path = service_config_dir / f"{env}.yaml"

    print(f"Loading config files:\n{service_base_yaml_path}\n{service_yaml_path}")

    # 3. Load and merge YAML configs
    merged_yaml_config = {}
    yaml_config_sources = [
        _load_yaml_config(base_yaml_path),
        _load_yaml_config(service_base_yaml_path),
        _load_yaml_config(service_yaml_path)
    ]

    for config_source in yaml_config_sources:
        if config_source:
            # Flatten and override
            merged_yaml_config.update(_flatten_nested_config(config_source))

    # 4. Build initial data
    initial_data = {
        "ENV": env,
        "CONSUMER": consumer,
        **merged_yaml_config
    }

    # 5. Validate and load via Pydantic (env vars override)
    try:
        _SETTINGS_INSTANCE = Settings.model_validate(initial_data)
        _SETTINGS_INITIALIZED = True
    except Exception as e:
        raise InitializationError(f"Pydantic settings validation failed: {e}")


# ----------------------------------------------------------------------
# 4. Singleton accessor
# ----------------------------------------------------------------------

def get_settings() -> 'Settings':
    """
    Return the global settings singleton.
    """
    global _SETTINGS_INSTANCE
    if _SETTINGS_INSTANCE is None:
        raise InitializationError("Settings not initialized. Call initialize_settings() on startup.")
    return _SETTINGS_INSTANCE
