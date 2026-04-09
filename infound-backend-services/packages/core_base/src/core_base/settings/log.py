from pydantic import Field

from . import SettingsBase


class LogSettings(SettingsBase):
    app_name: str = Field(default="app", validation_alias="app_name")
    level: str = "INFO"
    dir: str = "logs"
    file_max_size: int = 10
    file_backup_count: int = 30
