from pydantic_settings import BaseSettings, SettingsConfigDict

from core_base.base_constants import ENV_NESTED_DELIMITER


class SettingsBase(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter=ENV_NESTED_DELIMITER, case_sensitive=False, extra="ignore"
    )
