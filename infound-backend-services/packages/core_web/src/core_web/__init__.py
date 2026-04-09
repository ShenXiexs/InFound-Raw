# -*- coding: utf-8 -*-
"""
Core Web Package
================

Web 应用核心组件包，提供 FastAPI 应用工厂和基础配置。

本包包含：
- 应用工厂 (AppFactory) - 用于创建标准化的 FastAPI 应用
- 基础 Web 配置 - Web 应用的基础配置和异常处理
"""

# 版本信息
__version__ = "0.1.0"
__author__ = "Thomas Xing"
__description__ = "Web 项目公用类库"

# 导出应用工厂
from .app_factory import AppFactory
from .base_web_config import BaseWebAppSettings
from .exceptions import (
    AppException,
    ResourceNotFoundError,
    PermissionDeniedError,
    InitializationError,
    register_exception_handlers,
)
from .request_helper import get_request_domain

__all__ = [
    "AppFactory",
    "BaseWebAppSettings",
    "get_request_domain",
    "AppException",
    "ResourceNotFoundError",
    "PermissionDeniedError",
    "InitializationError",
    "register_exception_handlers",
]
