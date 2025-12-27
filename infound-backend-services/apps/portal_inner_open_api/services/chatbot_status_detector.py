from __future__ import annotations

from typing import Dict, List, Optional, Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.logger import get_logger
from common.models.infound import Samples, SampleCrawlLogs
from apps.portal_inner_open_api.services.chatbot_schedule_repository import (
    _normalize_status,
    _is_empty_content_summary,
    _is_ad_code_empty,
)

logger = get_logger()


class ChatbotStatusDetector:
    """
    Detect status changes keyed by username:sample_id.
    """

    @staticmethod
    def _make_key(username: Optional[str], sample_id: Optional[str]) -> Optional[str]:
        """Build unique key: username:sample_id."""
        if not username or not sample_id:
            return None
        return f"{username}:{sample_id}"

    async def get_current_samples_by_key(
        self, session: AsyncSession
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch current sample states from Samples, grouped by username:sample_id.

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

            # Build unique key: username:sample_id
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

        logger.info("Fetched current sample states", total_count=len(current_map))
        return current_map

    async def get_last_crawl_status_by_key(
        self, session: AsyncSession
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch last crawl states from SampleCrawlLogs, joined by username:sample_id.
        Uses Samples to find the latest crawl record per username:sample_id.

        Returns:
            {
                "username:sample_id": {
                    "status": "...",
                    "content_summary": {...},
                    "ad_code": {...}
                }
            }
        """
        # Query Samples to get sample_id and platform_creator_username
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
            logger.info("No valid sample records found")
            return {}

        # Map sample_id -> (platform_product_id, platform_creator_username)
        # SampleCrawlLogs does not store sample_id, only platform_product_id
        sample_to_product_username = {}
        for row in samples_rows:
            sample_id = row.id
            username = row.platform_creator_username
            product_id = row.platform_product_id
            
            if sample_id and username and product_id:
                sample_to_product_username[sample_id] = (product_id, username)
        
        if not sample_to_product_username:
            logger.info("No valid sample records found (missing platform_product_id)")
            return {}

        # Window function: latest crawl record per (platform_product_id, platform_creator_username)
        # Sort by most recent (crawl_date DESC, creation_time DESC)
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

        # Keep only latest record (rn=1)
        stmt = select(
            subquery.c.platform_product_id,
            subquery.c.platform_creator_username,
            subquery.c.status,
            subquery.c.content_summary,
            subquery.c.ad_code,
        ).where(subquery.c.rn == 1)

        result = await session.execute(stmt)
        rows = result.all()

        # Build mapping for (platform_product_id, platform_creator_username)
        product_username_to_status = {}
        for row in rows:
            key = (row.platform_product_id, row.platform_creator_username)
            product_username_to_status[key] = {
                "status": row.status,
                "content_summary": row.content_summary,
                "ad_code": row.ad_code,
            }

        # Map back to username:sample_id keys
        last_map = {}
        for sample_id, (product_id, username) in sample_to_product_username.items():
            key = (product_id, username)
            if key in product_username_to_status:
                username_sample_key = self._make_key(username, sample_id)
                if username_sample_key:
                    last_map[username_sample_key] = product_username_to_status[key]

        logger.info("Fetched last crawl states", total_count=len(last_map))
        return last_map

    def detect_status_changes(
        self,
        current_map: Dict[str, Dict[str, Any]],
        last_map: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Compare snapshots and return samples with state changes.

        Args:
            current_map: current state map keyed by username:sample_id
            last_map: previous state map keyed by username:sample_id

        Returns:
            [{
                "sample_id": "...",
                "scenario": "shipped|content_pending|no_content_posted|missing_ad_code",
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

            # Skip new samples not present in previous snapshot
            if last_info is None:
                continue

            prev_status = _normalize_status(last_info.get("status"))
            curr_status = _normalize_status(current_info.get("status"))

            # Detect status changes (one-time events)
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

            # Detect content summary changes (recurring reminders)
            if curr_status == "completed":
                prev_has_content = not _is_empty_content_summary(
                    last_info.get("content_summary")
                )
                curr_has_content = not _is_empty_content_summary(
                    current_info.get("content_summary")
                )

                # From content -> no content, or first time no content
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

            # Detect AD code changes (recurring reminders)
            prev_has_ad_code = not _is_ad_code_empty(last_info.get("ad_code"))
            curr_has_ad_code = not _is_ad_code_empty(current_info.get("ad_code"))

            # From AD code -> no AD code, or first time no AD code
            if (prev_has_ad_code and not curr_has_ad_code) or (
                last_info.get("ad_code") is None and not curr_has_ad_code
            ):
                changes.append(
                    {
                        "sample_id": current_info["sample_id"],
                        "scenario": "missing_ad_code",
                        "region": current_info.get("region"),
                        "platform_product_id": current_info["platform_product_id"],
                        "platform_creator_username": current_info[
                            "platform_creator_username"
                        ],
                        "platform_creator_id": current_info.get("platform_creator_id"),
                        "previous_status": last_info.get("status"),
                        "current_status": current_info.get("status"),
                    }
                )

        logger.info("Status change detection completed", changed_count=len(changes))
        return changes


# Singleton instance
chatbot_status_detector = ChatbotStatusDetector()

