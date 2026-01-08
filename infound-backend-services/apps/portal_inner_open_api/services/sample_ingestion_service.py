from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.config import get_settings
from common.core.logger import get_logger
from common.models.infound import (
    SampleContentCrawlLogs,
    SampleContents,
    SampleCrawlLogs,
    Samples,
)
from apps.portal_inner_open_api.services.chatbot_schedule_repository import (
    SampleSnapshot,
    chatbot_schedule_repository,
)
from apps.portal_inner_open_api.models.sample import (
    SampleIngestionRequest,
    SampleIngestionResult,
)

settings = get_settings()
logger = get_logger()


def _generate_uuid() -> str:
    return str(uuid4()).upper()


class SampleIngestionService:
    """Persist normalized rows from the crawler into MySQL."""

    def __init__(self) -> None:
        self.default_operator_id = (
            str(
                getattr(
                    settings,
                    "SAMPLE_DEFAULT_OPERATOR_ID",
                    "00000000-0000-0000-0000-000000000000",
                )
            )
            or "00000000-0000-0000-0000-000000000000"
        )
        self.default_region = str(
            getattr(settings, "SAMPLE_DEFAULT_REGION", "MX") or "MX"
        ).upper()

    async def ingest(
        self, request: SampleIngestionRequest, session: AsyncSession
    ) -> SampleIngestionResult:
        rows = [row.model_dump() for row in request.rows]
        if not rows:
            raise ValueError("rows cannot be empty")

        operator_id = request.operator_id or self.default_operator_id
        utc_now = datetime.utcnow()
        crawl_date = date.today()

        content_summary = self._build_content_summary_map(rows)
        products: Dict[str, Dict[str, Any]] = {}
        contents: List[Dict[str, Any]] = []
        for row in rows:
            product_id = row.get("platform_product_id")
            if not product_id:
                logger.warning("跳过缺少 platform_product_id 的行: %s", row)
                continue
            products[product_id] = row
            if row.get("type"):
                contents.append(row)

        if not products:
            raise ValueError("无法找到有效的样品商品数据")

        sample_snapshots: list[tuple[SampleSnapshot | None, SampleSnapshot]] = []
        for product_id, row in products.items():
            summary_entries = content_summary.get(product_id, [])
            payload = self._build_sample_payload(row, operator_id, utc_now, summary_entries)
            existing, previous_snapshot = await self._upsert_sample(session, payload)
            current_snapshot = SampleSnapshot(
                sample_id=existing.id,
                region=payload.get("region"),
                status=payload.get("status"),
                content_summary=payload.get("content_summary"),
                ad_code=payload.get("ad_code"),
                platform_product_id=existing.platform_product_id,
                platform_creator_username=existing.platform_creator_username,
                platform_creator_id=existing.platform_creator_id,
                platform_creator_display_name=existing.platform_creator_display_name,
            )
            sample_snapshots.append((previous_snapshot, current_snapshot))
        for row in rows:
            product_id = row.get("platform_product_id")
            summary_entries = content_summary.get(product_id, [])
            crawl_payload = self._build_sample_crawl_payload(
                row,
                operator_id,
                utc_now,
                crawl_date,
                summary_entries,
            )
            session.add(SampleCrawlLogs(**crawl_payload))

        for row in contents:
            content_payload = self._build_sample_content_payload(row, operator_id, utc_now)
            await self._upsert_sample_content(session, content_payload)
            content_log_payload = self._build_sample_content_log_payload(
                row,
                operator_id,
                utc_now,
                crawl_date,
            )
            session.add(SampleContentCrawlLogs(**content_log_payload))

        # Trigger chatbot schedules based on latest sample snapshot(s).
        for previous, current in sample_snapshots:
            try:
                await chatbot_schedule_repository.apply_sample_snapshot(
                    session, previous=previous, current=current
                )
            except Exception:
                logger.warning(
                    "Failed to update chatbot schedule (ignored)",
                    sample_id=current.sample_id,
                    scenario_hint="sample_ingest",
                    exc_info=True,
                )

        logger.info(
            "样品数据入库完成",
            source=request.source,
            rows=len(rows),
            products=len(products),
        )
        return SampleIngestionResult(inserted=len(rows), products=len(products))

    def _build_sample_payload(
        self,
        row: Dict[str, Any],
        operator_id: str,
        utc_now: datetime,
        summary_entries: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        platform_creator_display_name = self._extract_platform_creator_display_name(row)
        platform_creator_username = self._extract_platform_creator_username(row)
        platform_creator_id = self._extract_platform_creator_id(row, operator_id)
        return {
            "platform_product_id": row.get("platform_product_id"),
            "platform_campaign_id": self._safe_str(row.get("platform_campaign_id")),
            "platform_campaign_name": row.get("platform_campaign_name"),
            "region": self._safe_region(row.get("region")),
            "stock": self._coerce_int(row.get("stock")),
            "product_sku": self._safe_str(row.get("product_sku")),
            "available_sample_count": self._coerce_int(row.get("available_sample_count")),
            "is_uncooperative": self._coerce_bool(row.get("is_uncooperative")),
            "is_unapprovable": self._coerce_bool(row.get("is_unapprovable")),
            "status": self._safe_str(row.get("status")),
            "request_time_remaining": self._safe_str(row.get("request_time_remaining")),
            "platform_creator_display_name": platform_creator_display_name,
            "platform_creator_username": platform_creator_username,
            "platform_creator_id": platform_creator_id,
            "post_rate": self._coerce_decimal(row.get("post_rate")),
            "is_showcase": self._coerce_bool(row.get("is_showcase")),
            "content_summary": summary_entries or None,
            "ad_code": row.get("ad_code"),
            "creator_id": operator_id,
            "creation_time": utc_now,
            "last_modifier_id": operator_id,
            "last_modification_time": utc_now,
        }

    def _build_sample_crawl_payload(
        self,
        row: Dict[str, Any],
        operator_id: str,
        utc_now: datetime,
        crawl_date: date,
        summary_entries: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        platform_creator_display_name = self._extract_platform_creator_display_name(row)
        platform_creator_username = self._extract_platform_creator_username(row)
        platform_creator_id = self._extract_platform_creator_id(row, operator_id)
        return {
            "id": _generate_uuid(),
            "platform_product_id": row.get("platform_product_id"),
            "platform_campaign_id": self._safe_str(row.get("platform_campaign_id")),
            "platform_campaign_name": row.get("platform_campaign_name"),
            "region": self._safe_region(row.get("region")),
            "stock": self._coerce_int(row.get("stock")),
            "product_sku": self._safe_str(row.get("product_sku")),
            "available_sample_count": self._coerce_int(row.get("available_sample_count")),
            "is_uncooperative": self._coerce_bool(row.get("is_uncooperative")),
            "is_unapprovable": self._coerce_bool(row.get("is_unapprovable")),
            "status": self._safe_str(row.get("status")),
            "request_time_remaining": self._safe_str(row.get("request_time_remaining")),
            "platform_creator_display_name": platform_creator_display_name,
            "platform_creator_username": platform_creator_username,
            "platform_creator_id": platform_creator_id,
            "post_rate": self._coerce_decimal(row.get("post_rate")),
            "is_showcase": self._coerce_bool(row.get("is_showcase")),
            "content_summary": summary_entries or None,
            "ad_code": row.get("ad_code"),
            "crawl_date": crawl_date,
            "creator_id": operator_id,
            "creation_time": utc_now,
            "last_modifier_id": operator_id,
            "last_modification_time": utc_now,
        }

    def _build_sample_content_payload(
        self,
        row: Dict[str, Any],
        operator_id: str,
        utc_now: datetime,
    ) -> Dict[str, Any]:
        # 兼容历史数据：既支持 'video'/'live'，也支持 '1'/'2'
        content_type = self._safe_str(row.get("type"))
        normalized_type = None
        if content_type in {"video", "live"}:
            normalized_type = content_type
        elif content_type == "1":
            normalized_type = "video"
        elif content_type == "2":
            normalized_type = "live"

        platform_creator_display_name = self._extract_platform_creator_display_name(row)
        platform_creator_username = self._extract_platform_creator_username(row)
        platform_creator_id = self._extract_platform_creator_id(row, operator_id)
        creator_url = self._extract_creator_url(row)

        return {
            "platform_product_id": row.get("platform_product_id"),
            "platform_creator_id": platform_creator_id,
            "platform_creator_display_name": platform_creator_display_name,
            "platform_creator_username": platform_creator_username,
            "region": self._safe_region(row.get("region")),
            "type": normalized_type,
            "promotion_name": self._safe_str(row.get("promotion_name")),
            "promotion_time": self._safe_str(row.get("promotion_time")),
            "promotion_view_count": self._coerce_int(row.get("promotion_view_count")),
            "promotion_like_count": self._coerce_int(row.get("promotion_like_count")),
            "promotion_comment_count": self._coerce_int(row.get("promotion_comment_count")),
            "promotion_order_count": self._coerce_int(row.get("promotion_order_count")),
            "promotion_order_total_amount": self._coerce_decimal(row.get("promotion_order_total_amount")),
            "creator_id": operator_id,
            "creation_time": utc_now,
            "last_modifier_id": operator_id,
            "last_modification_time": utc_now,
        }

    def _build_sample_content_log_payload(
        self,
        row: Dict[str, Any],
        operator_id: str,
        utc_now: datetime,
        crawl_date: date,
    ) -> Dict[str, Any]:
        payload = self._build_sample_content_payload(row, operator_id, utc_now)
        payload.update({"id": _generate_uuid(), "crawl_date": crawl_date})
        return payload

    async def _upsert_sample(
        self, session: AsyncSession, payload: Dict[str, Any]
    ) -> tuple[Samples, SampleSnapshot | None]:
        stmt = select(Samples).where(
            Samples.platform_product_id == payload["platform_product_id"],
            Samples.platform_creator_display_name.is_(None)
            if payload.get("platform_creator_display_name") is None
            else Samples.platform_creator_display_name == payload.get("platform_creator_display_name"),
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            previous = SampleSnapshot(
                sample_id=existing.id,
                region=existing.region,
                status=existing.status,
                content_summary=existing.content_summary,
                ad_code=existing.ad_code,
                platform_product_id=existing.platform_product_id,
                platform_creator_username=existing.platform_creator_username,
                platform_creator_id=existing.platform_creator_id,
                platform_creator_display_name=existing.platform_creator_display_name,
            )
            for key, value in payload.items():
                if key in {"creator_id", "creation_time"}:
                    continue
                setattr(existing, key, value)
            return existing, previous

        data = {"id": _generate_uuid(), **payload}
        instance = Samples(**data)
        session.add(instance)
        return instance, None

    async def _upsert_sample_content(
        self,
        session: AsyncSession,
        payload: Dict[str, Any],
    ) -> None:
        def _eq_or_is_null(column, value: Any):
            return column.is_(None) if value is None else column == value

        stmt = (
            select(SampleContents)
            .where(
            SampleContents.platform_product_id == payload["platform_product_id"],
            _eq_or_is_null(SampleContents.promotion_name, payload.get("promotion_name")),
            _eq_or_is_null(SampleContents.promotion_time, payload.get("promotion_time")),
            _eq_or_is_null(SampleContents.type, payload.get("type")),
            )
            .order_by(SampleContents.last_modification_time.desc(), SampleContents.id.desc())
            .limit(2)
        )
        result = await session.execute(stmt)
        matches = list(result.scalars().all())
        existing = matches[0] if matches else None
        if len(matches) > 1:
            logger.warning(
                "sample_contents 检测到重复记录，将只更新最新一条",
                platform_product_id=payload.get("platform_product_id"),
                promotion_name=payload.get("promotion_name"),
                promotion_time=payload.get("promotion_time"),
                type=payload.get("type"),
                duplicates=len(matches),
            )
        if existing:
            for key, value in payload.items():
                if key in {"creator_id", "creation_time"}:
                    continue
                setattr(existing, key, value)
        else:
            data = {"id": _generate_uuid(), **payload}
            session.add(SampleContents(**data))

    def _build_content_summary_map(
        self,
        rows: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        summary: Dict[str, List[Dict[str, Any]]] = {}
        seen: Dict[str, Set[str]] = {}
        for row in rows:
            product_id = row.get("platform_product_id")
            if not product_id:
                continue
            entries = self._build_summary_entries_for_row(row)
            if not entries:
                summary.setdefault(product_id, [])
                continue
            bucket = summary.setdefault(product_id, [])
            bucket_seen = seen.setdefault(product_id, set())
            for entry in entries:
                serialized = json.dumps(entry, sort_keys=True, default=str, ensure_ascii=False)
                if serialized in bucket_seen:
                    continue
                bucket_seen.add(serialized)
                bucket.append(entry)
        for product_id, items in summary.items():
            if not items:
                items.append(self._empty_summary_entry())
        return summary

    def _build_summary_entries_for_row(self, row: Dict[str, Any]) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        promotion_fields = [
            row.get("type"),
            row.get("promotion_name"),
            row.get("promotion_time"),
            row.get("promotion_view_count"),
            row.get("promotion_like_count"),
            row.get("promotion_comment_count"),
            row.get("promotion_order_count"),
            row.get("promotion_order_total_amount"),
        ]
        if any(promotion_fields):
            entry = self._empty_summary_entry()
            entry.update(
                {
                    "type": row.get("type") or "",
                    "type_number": row.get("type_number") or "",
                    "promotion_name": row.get("promotion_name") or "",
                    "promotion_time": row.get("promotion_time") or "",
                    "promotion_view_count": row.get("promotion_view_count"),
                    "promotion_like_count": row.get("promotion_like_count"),
                    "promotion_comment_count": row.get("promotion_comment_count"),
                    "promotion_order_count": row.get("promotion_order_count"),
                    "promotion_order_total_amount": self._decimal_to_str(
                        row.get("promotion_order_total_amount")
                    ),
                }
            )
            entries.append(entry)

        logistics_snapshot = row.get("logistics_snapshot")
        if logistics_snapshot:
            entries.extend(self._logistics_summary_entries(logistics_snapshot))
        return entries

    def _logistics_summary_entries(self, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        timeline = snapshot.get("timeline") or []
        basic_pairs = snapshot.get("basic_info") or []
        base_label = ", ".join(
            f"{item.get('label')}: {item.get('value')}"
            for item in basic_pairs
            if item.get("label") or item.get("value")
        )

        if timeline:
            total = len(timeline)
            for event in timeline:
                entry = self._empty_summary_entry()
                entry.update(
                    {
                        "type": "logistics",
                        "type_number": str(total),
                        "promotion_name": event.get("title")
                        or event.get("status")
                        or base_label
                        or "Logistics update",
                        "promotion_time": event.get("time") or "",
                        "promotion_view_count": None,
                        "promotion_like_count": None,
                        "promotion_comment_count": None,
                        "promotion_order_count": None,
                        "promotion_order_total_amount": None,
                        "logistics_snapshot": snapshot,
                    }
                )
                entries.append(entry)
        elif base_label or snapshot.get("raw_text"):
            entry = self._empty_summary_entry()
            entry.update(
                {
                    "type": "logistics",
                    "type_number": str(len(basic_pairs)),
                    "promotion_name": base_label or "View logistics",
                    "promotion_time": "",
                    "promotion_view_count": None,
                    "promotion_like_count": None,
                    "promotion_comment_count": None,
                    "promotion_order_count": None,
                    "promotion_order_total_amount": None,
                    "logistics_snapshot": snapshot,
                }
            )
            entries.append(entry)
        return entries

    def _empty_summary_entry(self) -> Dict[str, Any]:
        return {
            "type": "",
            "type_number": "",
            "promotion_name": "",
            "promotion_time": "",
            "promotion_view_count": None,
            "promotion_like_count": None,
            "promotion_comment_count": None,
            "promotion_order_count": None,
            "promotion_order_total_amount": None,
            "logistics_snapshot": None,
        }

    def _decimal_to_str(self, value: Optional[Any]) -> Optional[str]:
        decimal_value = self._coerce_decimal(value)
        if decimal_value is None:
            return None
        return format(decimal_value, "f").rstrip("0").rstrip(".")

    def _coerce_int(self, value: Any) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _coerce_bool(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return 1 if value else 0
        lowered = str(value).strip().lower()
        if lowered in {"1", "true", "yes"}:
            return 1
        if lowered in {"0", "false", "no"}:
            return 0
        return None

    def _coerce_decimal(self, value: Any) -> Optional[Decimal]:
        if value is None or value == "":
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    def _safe_str(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _is_uuid_like(self, value: str) -> bool:
        value = value.strip()
        return len(value) == 36 and value.count("-") == 4

    def _extract_platform_creator_display_name(self, row: Dict[str, Any]) -> Optional[str]:
        return self._safe_str(
            row.get("platform_creator_display_name") or row.get("creator_name")
        )

    def _extract_platform_creator_username(self, row: Dict[str, Any]) -> Optional[str]:
        return self._safe_str(
            row.get("platform_creator_username") or row.get("creator_username")
        )

    def _extract_platform_creator_id(
        self, row: Dict[str, Any], operator_id: str
    ) -> Optional[str]:
        """
        Prefer platform creator id fields; fall back to crawler legacy keys.

        Note: operator_id is an internal UUID. Avoid mistakenly writing it into
        platform_creator_id when crawler payload uses 'creator_id' for operator id.
        """
        candidate = self._safe_str(row.get("platform_creator_id"))
        if candidate:
            return candidate

        candidate = self._safe_str(row.get("creator_id"))
        if not candidate:
            return None
        if candidate == operator_id or self._is_uuid_like(candidate):
            return None
        return candidate

    def _extract_creator_url(self, row: Dict[str, Any]) -> Optional[str]:
        return self._safe_str(row.get("creator_url") or row.get("platform_detail_url"))

    def _safe_region(self, region: Optional[str]) -> str:
        text = (region or self.default_region or "MX").strip()
        return text.upper() or self.default_region


sample_ingestion_service = SampleIngestionService()
