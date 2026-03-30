from pydantic import BaseModel, Field

from core_base.settings import SettingsBase
from core_redis.redis_setting import RedisSettings
from core_web import BaseWebAppSettings
from shared_domain.mysql_setting import MySQLSettings
from shared_infrastructure.settings.auth_config import IFAuthSettings


class IFRabbitMQWebSTOMPSettings(SettingsBase):
    host: str
    port: int
    stomp_port: int
    username: str
    password: str
    vhost: str
    exchange_name: str


class IFAliSmsSettings(SettingsBase):
    sign_name: str = "华钥"
    template_code: str = "SMS_501730123"
    access_key_id: str
    access_key_secret: str
    verification_code_expire_seconds: int = 300
    max_send_count_per_phone: int = 5
    send_count_window_seconds: int = 300


class SellerRpaSchedulerSettings(BaseModel):
    enabled: bool = True
    delayed_poll_interval_seconds: int = 5
    delayed_batch_size: int = 50
    dispatch_marker_ttl_seconds: int = 21600
    recovery_batch_size: int = 500
    sample_monitor_daily_enabled: bool = True
    sample_monitor_daily_timezone: str = "Asia/Shanghai"
    sample_monitor_daily_hour: int = 1
    sample_monitor_daily_minute: int = 10
    sample_monitor_daily_check_interval_seconds: int = 60
    sample_monitor_daily_tabs: list[str] = [
        "to_review",
        "ready_to_ship",
        "shipped",
        "in_progress",
        "completed",
    ]


class Settings(BaseWebAppSettings):
    mysql: MySQLSettings = Field(default_factory=MySQLSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    rabbitmq_web_stomp: IFRabbitMQWebSTOMPSettings = Field(default_factory=IFRabbitMQWebSTOMPSettings)
    auth: IFAuthSettings = Field(default_factory=IFAuthSettings)
    sms: IFAliSmsSettings = Field(default_factory=IFAliSmsSettings)
    seller_rpa_scheduler: SellerRpaSchedulerSettings = Field(
        default_factory=SellerRpaSchedulerSettings
    )
