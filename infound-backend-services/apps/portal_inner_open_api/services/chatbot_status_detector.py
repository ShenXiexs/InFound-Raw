from __future__ import annotations

from typing import Dict, List, Optional, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.logger import get_logger
from common.models.infound import Samples, SampleCrawlLogs
from apps.portal_inner_open_api.services.chatbot_schedule_repository import (
    _normalize_status,
    _is_empty_content_summary,
)

logger = get_logger()


class ChatbotStatusDetector:
    """
    基于 username:sample_id 的状态变更检测服务。
    """

    @staticmethod
    def _make_key(username: Optional[str], sample_id: Optional[str]) -> Optional[str]:
        """生成唯一键：username:sample_id"""
        if not username or not sample_id:
            return None
        return f"{username}:{sample_id}"

    async def get_current_samples_by_key(
        self, session: AsyncSession
    ) -> Dict[str, Dict[str, Any]]:
        """
        查询当前所有样品状态（从 Samples 表），按 username:sample_id 分组。

        Returns:
            {
                "username:sample_id": {
                    "sample_id": "...",
                    "status": "...",
                    "region": "...",
                    "platform_product_id": "...",
                    "platform_creator_username": "...",
                    "platform_creator_id": "...",
                    "content_summary": {...},
                    "ad_code": {...}
                }
            }
        """
        stmt = (
            select(
                Samples.id,
                Samples.platform_product_id,
                Samples.platform_creator_username,
                Samples.platform_creator_id,
                Samples.status,
                Samples.region,
                Samples.content_summary,
                Samples.ad_code,
            )
            .where(
                Samples.platform_product_id.isnot(None),
                Samples.platform_creator_username.isnot(None),
            )
        )

        result = await session.execute(stmt)
        rows = result.all()

        current_map = {}
        for row in rows:
            sample_id = row.id
            username = row.platform_creator_username
            if not sample_id or not username:
                continue

            # 生成唯一键：username:sample_id
            key = self._make_key(username, sample_id)
            if not key:
                continue

            current_map[key] = {
                "sample_id": sample_id,
                "status": row.status,
                "region": row.region,
                "platform_product_id": row.platform_product_id,
                "platform_creator_username": username,
                "platform_creator_id": row.platform_creator_id,
                "content_summary": row.content_summary,
                "ad_code": row.ad_code,
            }

        logger.info("查询当前样品状态完成", total_count=len(current_map))
        return current_map

    async def get_last_crawl_status_by_key(
        self, session: AsyncSession
    ) -> Dict[str, Dict[str, Any]]:
        """
        查询上次爬取时的状态（从 SampleCrawlLogs 表），按 username:sample_id 关联。
        通过 Samples 表关联 SampleCrawlLogs，找到每个 username:sample_id 对应的最新 SampleCrawlLogs 记录（时间最近的）。

        Returns:
            {
                "username:sample_id": {
                    "status": "...",
                    "content_summary": {...},
                    "ad_code": {...}
                }
            }
        """
        # 先查询 Samples 表，获取所有 sample_id 及其对应的 platform_creator_username
        samples_stmt = select(
            Samples.id,
            Samples.platform_creator_username,
            Samples.platform_product_id,
        ).where(
            Samples.platform_creator_username.isnot(None),
        )
        
        samples_result = await session.execute(samples_stmt)
        samples_rows = samples_result.all()
        
        if not samples_rows:
            logger.info("没有找到有效的样品记录")
            return {}
        
        # 构建 sample_id 到 (platform_product_id, platform_creator_username) 的映射
        # 用于后续关联 SampleCrawlLogs（因为 SampleCrawlLogs 没有 sample_id，只有 platform_product_id）
        sample_to_product_username = {}
        for row in samples_rows:
            sample_id = row.id
            username = row.platform_creator_username
            product_id = row.platform_product_id
            
            if sample_id and username and product_id:
                sample_to_product_username[sample_id] = (product_id, username)
        
        if not sample_to_product_username:
            logger.info("没有找到有效的样品记录（缺少 platform_product_id）")
            return {}
        
        # 使用窗口函数找出每个 (platform_product_id, platform_creator_username) 组合的最新爬取记录
        # 按时间最近的排序（crawl_date DESC, creation_time DESC）
        subquery = (
            select(
                SampleCrawlLogs.platform_product_id,
                SampleCrawlLogs.platform_creator_username,
                SampleCrawlLogs.status,
                SampleCrawlLogs.content_summary,
                SampleCrawlLogs.ad_code,
                SampleCrawlLogs.crawl_date,
                SampleCrawlLogs.creation_time,
                func.row_number()
                .over(
                    partition_by=[
                        SampleCrawlLogs.platform_product_id,
                        SampleCrawlLogs.platform_creator_username,
                    ],
                    order_by=[
                        SampleCrawlLogs.crawl_date.desc(),
                        SampleCrawlLogs.creation_time.desc(),
                    ],
                )
                .label("rn"),
            )
            .where(
                SampleCrawlLogs.platform_product_id.isnot(None),
                SampleCrawlLogs.platform_creator_username.isnot(None),
            )
            .subquery()
        )

        # 只取每个组合的最新记录（rn=1）
        stmt = select(
            subquery.c.platform_product_id,
            subquery.c.platform_creator_username,
            subquery.c.status,
            subquery.c.content_summary,
            subquery.c.ad_code,
        ).where(subquery.c.rn == 1)

        result = await session.execute(stmt)
        rows = result.all()

        # 构建 (platform_product_id, platform_creator_username) 到状态的映射
        product_username_to_status = {}
        for row in rows:
            key = (row.platform_product_id, row.platform_creator_username)
            product_username_to_status[key] = {
                "status": row.status,
                "content_summary": row.content_summary,
                "ad_code": row.ad_code,
            }

        # 通过 sample_id 映射到状态，构建 username:sample_id 为 key 的字典
        last_map = {}
        for sample_id, (product_id, username) in sample_to_product_username.items():
            key = (product_id, username)
            if key in product_username_to_status:
                username_sample_key = self._make_key(username, sample_id)
                if username_sample_key:
                    last_map[username_sample_key] = product_username_to_status[key]

        logger.info("查询上次爬取状态完成", total_count=len(last_map))
        return last_map

    def detect_status_changes(
        self,
        current_map: Dict[str, Dict[str, Any]],
        last_map: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        对比两次快照，找出状态变化的样品。

        Args:
            current_map: 当前状态，key 为 username:sample_id
            last_map: 上次状态，key 为 username:sample_id

        Returns:
            [{
                "sample_id": "...",
                "scenario": "shipped|content_pending|no_content_posted",
                "region": "...",
                "platform_product_id": "...",
                "platform_creator_username": "...",
                "platform_creator_id": "...",
                "previous_status": "...",
                "current_status": "..."
            }, ...]
        """
        changes = []

        for key, current_info in current_map.items():
            last_info = last_map.get(key)

            # 如果上次快照里没有（新样品），跳过
            if last_info is None:
                continue

            prev_status = _normalize_status(last_info.get("status"))
            curr_status = _normalize_status(current_info.get("status"))

            # 检测状态变更（一次性事件）
            if prev_status and curr_status and prev_status != curr_status:
                if curr_status == "shipped":
                    changes.append(
                        {
                            "sample_id": current_info["sample_id"],
                            "scenario": "shipped",
                            "region": current_info.get("region"),
                            "platform_product_id": current_info["platform_product_id"],
                            "platform_creator_username": current_info[
                                "platform_creator_username"
                            ],
                            "platform_creator_id": current_info.get(
                                "platform_creator_id"
                            ),
                            "previous_status": last_info.get("status"),
                            "current_status": current_info.get("status"),
                        }
                    )
                elif curr_status == "content pending":
                    changes.append(
                        {
                            "sample_id": current_info["sample_id"],
                            "scenario": "content_pending",
                            "region": current_info.get("region"),
                            "platform_product_id": current_info["platform_product_id"],
                            "platform_creator_username": current_info[
                                "platform_creator_username"
                            ],
                            "platform_creator_id": current_info.get(
                                "platform_creator_id"
                            ),
                            "previous_status": last_info.get("status"),
                            "current_status": current_info.get("status"),
                        }
                    )

            # 检测内容摘要变化（重复提醒）
            if curr_status == "completed":
                prev_has_content = not _is_empty_content_summary(
                    last_info.get("content_summary")
                )
                curr_has_content = not _is_empty_content_summary(
                    current_info.get("content_summary")
                )

                # 从有内容变为无内容，或首次检测到无内容
                if (prev_has_content and not curr_has_content) or (
                    last_info.get("content_summary") is None
                    and not curr_has_content
                ):
                    changes.append(
                        {
                            "sample_id": current_info["sample_id"],
                            "scenario": "no_content_posted",
                            "region": current_info.get("region"),
                            "platform_product_id": current_info["platform_product_id"],
                            "platform_creator_username": current_info[
                                "platform_creator_username"
                            ],
                            "platform_creator_id": current_info.get(
                                "platform_creator_id"
                            ),
                            "previous_status": last_info.get("status"),
                            "current_status": current_info.get("status"),
                        }
                    )

        logger.info("状态变更检测完成", changed_count=len(changes))
        return changes


# 单例实例
chatbot_status_detector = ChatbotStatusDetector()

