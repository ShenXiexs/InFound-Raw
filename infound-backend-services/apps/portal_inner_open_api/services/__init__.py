# -*- coding: utf-8 -*-
"""
Portal Inner Open API Services
==============================

内部开放 API 服务层，提供核心业务逻辑处理。

本包包含：
- 数据采集服务 (Ingestion Services)：Campaign、Creator、Sample 等数据抓取与入库
- Chatbot 服务：聊天机器人消息构建、调度、状态检测
- Outreach 服务：外展任务和创作者外展管理
- 历史服务：创作者历史记录管理
"""

# 版本信息
__version__ = "0.1.0"
__author__ = "Thomas"
__email__ = "tanher@qq.com"
__description__ = "内部开放 API 服务层"

# 导出数据采集服务
from .campaign_ingestion_service import CampaignIngestionService

# 导出 Chatbot 相关服务
from .chatbot_message_builder import ChatbotMessageBuilder
from .chatbot_schedule_publisher import ChatbotSchedulePublisher
from .chatbot_schedule_repository import ChatbotScheduleRepository
from .chatbot_status_detector import ChatbotStatusDetector

# 导出其他服务
from .creator_history_service import CreatorHistoryService
from .creator_ingestion_service import CreatorIngestionService

# 导出 Outreach 相关服务
from .outreach_creator_ingestion_service import OutreachCreatorIngestionService
from .outreach_task_service import OutreachTaskService
from .sample_ingestion_service import SampleIngestionService

__all__ = [
    # 数据采集服务
    "CampaignIngestionService",
    "CreatorIngestionService",
    "SampleIngestionService",
    # Chatbot 服务
    "ChatbotMessageBuilder",
    "ChatbotSchedulePublisher",
    "ChatbotScheduleRepository",
    "ChatbotStatusDetector",
    # Outreach 服务
    "OutreachCreatorIngestionService",
    "OutreachTaskService",
    # 其他服务
    "CreatorHistoryService",
]
