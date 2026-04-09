from pydantic import Field

from core_base.settings import SettingsBase, LogSettings


class BaseAppSettings(SettingsBase):
    """最基础的配置，所有项目共有"""

    app_name: str = "Infound Service"
    env: str = "dev"
    debug: bool = True

    # 唯一个必有的组件
    log: LogSettings = Field(default_factory=LogSettings)
