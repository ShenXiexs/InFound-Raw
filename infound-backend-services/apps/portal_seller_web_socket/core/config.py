from pydantic import Field

from core_base.settings import SettingsBase
from core_redis.redis_setting import RedisSettings
from core_web import BaseWebAppSettings
from shared_domain.mysql_setting import MySQLSettings
from shared_infrastructure.settings.auth_config import IFAuthSettings


class IFRabbitMQWebSTOMPSettings(SettingsBase):
    host: str
    port: int
    username: str
    password: str
    vhost: str
    exchange_name: str


class Settings(BaseWebAppSettings):
    mysql: MySQLSettings = Field(default_factory=MySQLSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    rabbitmq_web_stomp: IFRabbitMQWebSTOMPSettings = Field(default_factory=IFRabbitMQWebSTOMPSettings)
    auth: IFAuthSettings = Field(default_factory=IFAuthSettings)
