from pydantic import Field

from apps.portal_seller_open_api.core.config import Settings as SellerOpenApiSettings
from core_base.settings import SettingsBase


class SchedulerExecutorSettings(SettingsBase):
    """调度器执行器配置子模型"""
    type: str = Field(default="asyncio")
    max_workers: int = Field(default=10)


class SchedulerJobSettings(SettingsBase):
    """调度器任务默认配置子模型"""
    coalesce: bool = Field(default=False)
    max_instances: int = Field(default=3)


class SchedulerSettings(SettingsBase):
    """调度器主配置模型"""
    timezone: str = Field(default="Asia/Shanghai")
    executor: SchedulerExecutorSettings = Field(
        default_factory=SchedulerExecutorSettings
    )
    job: SchedulerJobSettings = Field(
        default_factory=SchedulerJobSettings
    )


class Settings(SellerOpenApiSettings):
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
