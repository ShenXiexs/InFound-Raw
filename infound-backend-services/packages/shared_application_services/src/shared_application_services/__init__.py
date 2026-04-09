# -*- coding: utf-8 -*-
"""
Shared Application Services Package
=====================

共享应用服务组件。

"""

# 版本信息
__version__ = "0.1.0"
__author__ = "Thomas"
__email__ = "tanher@qq.com"
__description__ = "共享应用服务组件"

from .dtos.base import (
    BaseDTO,
    CleanStr,
    FlexibleInt,
    PercentStr,
    PeriodList,
    FlexibleDatetime,
    FlexibleDecimal,
)

__all__ = [
    "BaseDTO",
    "CleanStr",
    "FlexibleInt",
    "PercentStr",
    "PeriodList",
    "FlexibleDatetime",
    "FlexibleDecimal",
]
