# -*- coding: utf-8 -*-
"""
Shared Domain Package
=====================

共享领域模型组件，提供通用的业务实体和数据库访问功能。

本包包含：
- 领域模型 (models)：Campaigns, Creators, ChatMessages 等实体
- 数据库管理 (database)：异步数据库连接管理
"""

# 版本信息
__version__ = "0.1.0"
__author__ = "Thomas"
__email__ = "tanher@qq.com"
__description__ = "共享领域模型组件"

# 导出数据库管理模块
from . import database

# 导出模型模块
from . import models
from .database import DatabaseManager
from .models.infound import (
    Base,
    Campaigns,
    ChatMessages,
    CreatorCrawlLogs,
    Creators,
    OpsUsers,
    SellerTkOutreachCreatorCounts,
    SellerTkOutreachSettings,
    SellerTkOutreachTaskLogs,
    SellerTkProducts,
    SellerTkRpaTaskPlans,
    SellerTkSampleContentCrawlLogs,
    SellerTkSampleContents,
    SellerTkSampleCrawlLogs,
    SellerTkSamples,
    SellerTkShops,
)

__all__ = [
    # 数据库组件
    "database",
    "DatabaseManager",
    # 模型模块
    "models",
    # 实体类
    "Base",
    "Campaigns",
    "ChatMessages",
    "CreatorCrawlLogs",
    "Creators",
    "OpsUsers",
    "SellerTkOutreachCreatorCounts",
    "SellerTkOutreachSettings",
    "SellerTkOutreachTaskLogs",
    "SellerTkProducts",
    "SellerTkRpaTaskPlans",
    "SellerTkSampleContentCrawlLogs",
    "SellerTkSampleContents",
    "SellerTkSampleCrawlLogs",
    "SellerTkSamples",
    "SellerTkShops",
]
