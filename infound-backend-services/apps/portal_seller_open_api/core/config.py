from pydantic import BaseModel, Field

from core_mq.rabbitmq_setting import RabbitMQSettings
from core_redis.redis_setting import RedisSettings
from core_web import BaseWebAppSettings
from shared_domain.mysql_setting import MySQLSettings
from shared_infrastructure.settings.auth_config import IFAuthSettings


class SellerRpaSchedulerSettings(BaseModel):
    enabled: bool = True
    delayed_poll_interval_seconds: int = 5
    delayed_batch_size: int = 50
    dispatch_marker_ttl_seconds: int = 21600
    recovery_batch_size: int = 500


class Settings(BaseWebAppSettings):
    mysql: MySQLSettings = Field(default_factory=MySQLSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    rabbitmq: RabbitMQSettings = Field(default_factory=RabbitMQSettings)
    auth: IFAuthSettings = Field(default_factory=IFAuthSettings)
    seller_rpa_scheduler: SellerRpaSchedulerSettings = Field(
        default_factory=SellerRpaSchedulerSettings
    )
