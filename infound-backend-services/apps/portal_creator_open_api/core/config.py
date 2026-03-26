from pydantic import Field

from core_redis.redis_setting import RedisSettings
from core_web import BaseWebAppSettings
from shared_domain.mysql_setting import MySQLSettings
from shared_infrastructure.settings.auth_config import IFAuthSettings


class Settings(BaseWebAppSettings):
    mysql: MySQLSettings = Field(default_factory=MySQLSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    auth: IFAuthSettings = Field(default_factory=IFAuthSettings)
