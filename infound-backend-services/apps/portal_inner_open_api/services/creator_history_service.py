from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.infound import CreatorCrawlLogs
from apps.portal_inner_open_api.models.creator import (
    CreatorHistoryRequest,
    CreatorHistoryResult,
    CreatorHistoryItem,
)


def _to_bool(value: Optional[object]) -> bool:
    if value is None:
        return False
    try:
        return bool(int(value))
    except Exception:
        return bool(value)


class CreatorHistoryService:
    """Query creator outreach history from crawl logs."""

    async def fetch(
        self, request: CreatorHistoryRequest, session: AsyncSession
    ) -> CreatorHistoryResult:
        normalized_name = (request.creator_name or "").strip().lower()
        normalized_username = (request.creator_username or "").strip().lower()

        conditions = []
        if request.creator_id:
            conditions.append(CreatorCrawlLogs.platform_creator_id == request.creator_id)
        if normalized_name:
            conditions.append(
                func.lower(CreatorCrawlLogs.platform_creator_display_name) == normalized_name
            )
            conditions.append(
                func.lower(CreatorCrawlLogs.platform_creator_username) == normalized_name
            )
        if normalized_username:
            conditions.append(
                func.lower(CreatorCrawlLogs.platform_creator_username) == normalized_username
            )

        if not conditions:
            raise ValueError("creator_id or creator_name/creator_username is required")

        stmt = (
            select(
                CreatorCrawlLogs.connect,
                CreatorCrawlLogs.reply,
                CreatorCrawlLogs.brand_name,
            )
            .where(or_(*conditions))
            .order_by(CreatorCrawlLogs.creation_time.desc())
            .limit(request.limit)
        )
        result = await session.execute(stmt)
        rows = result.mappings().all()

        records: List[CreatorHistoryItem] = []
        for row in rows:
            records.append(
                CreatorHistoryItem(
                    connect=_to_bool(row.get("connect")),
                    reply=_to_bool(row.get("reply")),
                    brand_name=row.get("brand_name"),
                )
            )

        return CreatorHistoryResult(records=records)


creator_history_service = CreatorHistoryService()
