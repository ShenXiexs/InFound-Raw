from core_base import BaseAppSettings


class BaseWebAppSettings(BaseAppSettings):
    cors_allow_origins: list = ["*"]
