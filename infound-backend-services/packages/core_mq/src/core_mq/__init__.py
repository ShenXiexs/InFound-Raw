# -*- coding: utf-8 -*-
"""
Core MQ Package
===============

消息队列核心组件，提供 RabbitMQ 连接、生产者和消费者基础功能。

本包包含：
- 连接管理 (connection)
- 生产者基类 (producer_base)
- 消费者基类 (consumer_base)
- 异常定义 (exceptions)
"""

# 版本信息
__version__ = "0.1.0"
__author__ = "Thomas"
__email__ = "tanher@qq.com"
__description__ = "消息队列核心组件"

# 导出连接模块
from . import connection

# 导出消费者基类
from . import consumer_base

# 导出生产者基类
from . import producer_base
from .connection import RabbitMQConnection
from .consumer_base import ConsumerBase, _parse_message_body

# 导出异常
from .exceptions import (
    RabbitMQConnectionError,
    MessageProcessingError,
)
from .producer_base import ProducerBase

__all__ = [
    # 连接组件
    "connection",
    "RabbitMQConnection",
    # 生产者组件
    "producer_base",
    "ProducerBase",
    # 消费者组件
    "consumer_base",
    "ConsumerBase",
    "_parse_message_body",
    # 异常
    "RabbitMQConnectionError",
    "MessageProcessingError",
]
