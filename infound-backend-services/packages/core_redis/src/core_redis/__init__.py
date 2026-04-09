# -*- coding: utf-8 -*-
"""
Core Redis Package
==================

Redis 核心组件，提供 Redis 客户端管理和连接池功能。

本包包含：
- Redis 客户端管理器 (redis_client)：单例模式管理连接池和客户端实例
- 依赖注入函数：用于 FastAPI 等框架的依赖注入
"""

# 版本信息
__version__ = "0.1.0"
__author__ = "Thomas"
__email__ = "tanher@qq.com"
__description__ = "Redis 核心组件"

# 导出 Redis 客户端管理模块
from . import redis_manager
from .redis_manager import RedisClientManager

__all__ = [
    # Redis 客户端管理组件
    "RedisClientManager",
]
