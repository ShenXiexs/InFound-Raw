from pathlib import Path
from typing import Type, TypeVar, Optional, Dict, Any, Generic

from ruamel.yaml import YAML

yaml = YAML(typ="safe")

from .base_config import BaseAppSettings

T = TypeVar("T", bound=BaseAppSettings)


class SettingsFactory(Generic[T]):
    _instance: Optional[BaseAppSettings] = None

    @classmethod
    def initialize(cls, settings_class: Type[T], config_dir: Path) -> T:
        """
        核心初始化方法
        :param settings_class: 传入具体的配置类（如 api_1.config.Settings）
        :param config_dir: 配置文件路径
        """
        # 1. 加载 YAML 逻辑 (复用之前的 _deep_merge 和 _load_yaml)
        # ... 加载 common/base.yaml 和 apps/xxx/configs/*.yaml ...
        config_data = cls._load_all_yaml(config_dir)

        # 3. 实例化子类
        cls._instance = settings_class(**config_data)

        return cls._instance

    @classmethod
    def _load_all_yaml(cls, config_dir: Path) -> Dict[str, Any]:
        import os

        env = os.getenv("ENV", os.getenv("env", "dev"))
        merged_data: Dict[str, Any] = {}

        # 待加载的文件顺序（后者覆盖前者）
        # 1. Common Base -> 2. App Base -> 3. App Env (dev/prod)
        search_paths = [config_dir / "base.yaml", config_dir / f"{env}.yaml"]

        for path in search_paths:
            if path and path.exists():
                file_data = cls._read_yaml(path)
                cls._deep_merge(merged_data, file_data)

        return merged_data

    @staticmethod
    def _read_yaml(path: Path) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.load(f) or {}
        except Exception as e:
            print(f"警告: 读取配置文件 {path} 失败: {e}")
            return {}

    @staticmethod
    def _deep_merge(base: Dict[str, Any], update: Dict[str, Any]) -> None:
        """深度合并字典 (In-place)"""
        for k, v in update.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                SettingsFactory._deep_merge(base[k], v)
            else:
                base[k] = v

    @classmethod
    def get_settings(cls) -> BaseAppSettings:
        if not cls._instance:
            raise RuntimeError("Settings not initialized!")
        return cls._instance

    @classmethod
    def get_typed_settings(cls, settings_type: Type[T]) -> T:
        """获取类型化的配置实例"""
        if not cls._instance:
            raise RuntimeError("Settings not initialized!")
        if not isinstance(cls._instance, settings_type):
            raise TypeError(
                f"Expected settings type {settings_type}, "
                f"but got {type(cls._instance)}"
            )
        return cls._instance  # type: ignore
