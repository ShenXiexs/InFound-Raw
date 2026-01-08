from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Any, Dict, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.logger import get_logger
from common.models.infound import Creators, CreatorCrawlLogs
from apps.portal_inner_open_api.models.creator import (
    CreatorIngestionRequest,
    CreatorIngestionResult,
)

logger = get_logger()

PREFERRED_UUID_NODE = 0x2AA7A70856D4


def _generate_uuid(value: Optional[str] = None) -> str:
    if value:
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, value)).upper()
    return str(uuid.uuid1(node=PREFERRED_UUID_NODE)).upper()


def _normalize_uuid_text(value: Any) -> str:
    if value is None:
        return _generate_uuid()
    if isinstance(value, uuid.UUID):
        return str(value).upper()
    text = str(value).strip()
    if not text:
        return _generate_uuid()
    try:
        return str(uuid.UUID(text)).upper()
    except Exception:
        return _generate_uuid(text)


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_region(value: Any) -> Optional[str]:
    text = _clean_text(value)
    return text.upper() if text else None


def _currency_for_region(region: Optional[str]) -> Optional[str]:
    normalized = (region or "").strip().upper()
    if not normalized:
        return None
    if normalized in {"FR", "ES", "EU"}:
        return "EU"
    if normalized in {"MX", "MEX"}:
        return "MXN"
    return None


def _parse_human_number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)

    raw = str(value).strip()
    if not raw:
        return None

    cleaned = (
        raw.replace(",", "")
        .replace(" ", "")
        .replace("\u00A0", "")
        .replace("$", "")
        .replace("\u20ac", "")
        .replace("\u00a3", "")
        .replace("\u00a5", "")
    )

    match = re.search(r"(-?\d+(?:\.\d+)?)([kKmMbBtT]?)", cleaned)
    if not match:
        return None

    number = float(match.group(1))
    suffix = (match.group(2) or "").lower()
    multiplier = {
        "": 1.0,
        "k": 1_000.0,
        "m": 1_000_000.0,
        "b": 1_000_000_000.0,
        "t": 1_000_000_000_000.0,
    }.get(suffix, 1.0)
    return number * multiplier


def _to_int(value: Any) -> Optional[int]:
    try:
        parsed = _parse_human_number(value)
        if parsed is None:
            return None
        return int(parsed)
    except Exception:
        return None


def _to_decimal(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            value = value.replace("%", "").strip()
        parsed = _parse_human_number(value)
        if parsed is None:
            return None
        return float(parsed)
    except Exception:
        return None


def _to_bool_flag(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return 1 if int(value) != 0 else 0
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y"}:
        return 1
    if text in {"0", "false", "no", "n"}:
        return 0
    return None


def _parse_crawl_date(value: Any, fallback: date) -> date:
    if isinstance(value, date):
        return value
    if value:
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return fallback


def _prepare_creator_payload(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    platform = _clean_text(row.get("platform")) or "tiktok"
    platform_creator_id = _clean_text(
        row.get("platform_creator_id") or row.get("creator_id")
    )
    if not platform_creator_id:
        return None
    stable_id = _generate_uuid(f"{platform}:{platform_creator_id}")
    username = _clean_text(
        row.get("platform_creator_username") or row.get("creator_username")
    )
    display_name = _clean_text(
        row.get("platform_creator_display_name") or row.get("creator_name")
    )
    if not username:
        username = display_name or platform_creator_id or "UNKNOWN_CREATOR"
    if not display_name:
        display_name = username

    region = _safe_region(row.get("region"))
    currency = _clean_text(row.get("currency"))
    if not currency:
        currency = _currency_for_region(region)

    return {
        "id": stable_id,
        "platform": platform,
        "platform_creator_id": platform_creator_id,
        "platform_creator_display_name": display_name,
        "platform_creator_username": username,
        "email": _clean_text(row.get("email")),
        "whatsapp": _clean_text(row.get("whatsapp")),
        "introduction": _clean_text(row.get("intro")),
        "region": region,
        "currency": currency,
        "categories": _clean_text(row.get("categories")),
        "chat_url": _clean_text(row.get("creator_chaturl")),
        "search_keywords": _clean_text(row.get("search_keywords")),
        "brand_name": _clean_text(row.get("brand_name")),
        "followers": _to_int(row.get("followers")),
        "top_brands": _clean_text(row.get("top_brands")),
        "sales_revenue": _to_decimal(row.get("sales_revenue")),
        "sales_units_sold": _to_int(row.get("sales_units_sold")),
        "sales_gpm": _to_decimal(row.get("sales_gpm")),
        "sales_revenue_per_buyer": _to_decimal(row.get("sales_revenue_per_buyer")),
        "gmv_per_sales_channel": _clean_text(row.get("gmv_per_sales_channel")),
        "gmv_by_product_category": _clean_text(row.get("gmv_by_product_category")),
        "avg_commission_rate": _to_decimal(row.get("avg_commission_rate")),
        "collab_products": _to_int(row.get("collab_products")),
        "partnered_brands": _to_int(row.get("partnered_brands")),
        "product_price": _clean_text(row.get("product_price")),
        "video_gpm": _to_decimal(row.get("video_gpm")),
        "videos": _to_int(row.get("videos")),
        "avg_video_views": _to_int(row.get("avg_video_views")),
        "avg_video_engagement_rate": _to_decimal(row.get("avg_video_engagement_rate")),
        "avg_video_likes": _to_int(row.get("avg_video_likes")),
        "avg_video_comments": _to_int(row.get("avg_video_comments")),
        "avg_video_shares": _to_int(row.get("avg_video_shares")),
        "live_gpm": _to_decimal(row.get("live_gpm")),
        "live_streams": _to_int(row.get("live_streams")),
        "avg_live_views": _to_int(row.get("avg_live_views")),
        "avg_live_engagement_rate": _to_decimal(row.get("avg_live_engagement_rate")),
        "avg_live_likes": _to_int(row.get("avg_live_likes")),
        "avg_live_comments": _to_int(row.get("avg_live_comments")),
        "avg_live_shares": _to_int(row.get("avg_live_shares")),
        "followers_male": _to_decimal(row.get("followers_male")),
        "followers_female": _to_decimal(row.get("followers_female")),
        "followers_18_24": _to_decimal(row.get("followers_18_24")),
        "followers_25_34": _to_decimal(row.get("followers_25_34")),
        "followers_35_44": _to_decimal(row.get("followers_35_44")),
        "followers_45_54": _to_decimal(row.get("followers_45_54")),
        "followers_55_more": _to_decimal(row.get("followers_55_more")),
    }


def _build_crawl_log_payload(
    row: Dict[str, Any],
    base_payload: Dict[str, Any],
    audit_id: str,
    utc_now: datetime,
    crawl_date: date,
    task_id: Optional[str],
) -> Dict[str, Any]:
    return {
        "id": _generate_uuid(),
        "crawl_date": _parse_crawl_date(row.get("crawl_date"), crawl_date),
        "platform": base_payload.get("platform"),
        "platform_creator_id": base_payload.get("platform_creator_id"),
        "platform_creator_display_name": base_payload.get("platform_creator_display_name"),
        "platform_creator_username": base_payload.get("platform_creator_username"),
        "task_id": task_id,
        "email": base_payload.get("email"),
        "whatsapp": base_payload.get("whatsapp"),
        "introduction": base_payload.get("introduction"),
        "region": base_payload.get("region"),
        "currency": base_payload.get("currency"),
        "categories": base_payload.get("categories"),
        "chat_url": base_payload.get("chat_url"),
        "search_keywords": base_payload.get("search_keywords"),
        "brand_name": base_payload.get("brand_name"),
        "followers": base_payload.get("followers"),
        "top_brands": base_payload.get("top_brands"),
        "sales_revenue": base_payload.get("sales_revenue"),
        "sales_units_sold": base_payload.get("sales_units_sold"),
        "sales_gpm": base_payload.get("sales_gpm"),
        "sales_revenue_per_buyer": base_payload.get("sales_revenue_per_buyer"),
        "gmv_per_sales_channel": base_payload.get("gmv_per_sales_channel"),
        "gmv_by_product_category": base_payload.get("gmv_by_product_category"),
        "avg_commission_rate": base_payload.get("avg_commission_rate"),
        "collab_products": base_payload.get("collab_products"),
        "partnered_brands": base_payload.get("partnered_brands"),
        "product_price": base_payload.get("product_price"),
        "video_gpm": base_payload.get("video_gpm"),
        "videos": base_payload.get("videos"),
        "avg_video_views": base_payload.get("avg_video_views"),
        "avg_video_engagement_rate": base_payload.get("avg_video_engagement_rate"),
        "avg_video_likes": base_payload.get("avg_video_likes"),
        "avg_video_comments": base_payload.get("avg_video_comments"),
        "avg_video_shares": base_payload.get("avg_video_shares"),
        "live_gpm": base_payload.get("live_gpm"),
        "live_streams": base_payload.get("live_streams"),
        "avg_live_views": base_payload.get("avg_live_views"),
        "avg_live_engagement_rate": base_payload.get("avg_live_engagement_rate"),
        "avg_live_likes": base_payload.get("avg_live_likes"),
        "avg_live_comments": base_payload.get("avg_live_comments"),
        "avg_live_shares": base_payload.get("avg_live_shares"),
        "followers_male": base_payload.get("followers_male"),
        "followers_female": base_payload.get("followers_female"),
        "followers_18_24": base_payload.get("followers_18_24"),
        "followers_25_34": base_payload.get("followers_25_34"),
        "followers_35_44": base_payload.get("followers_35_44"),
        "followers_45_54": base_payload.get("followers_45_54"),
        "followers_55_more": base_payload.get("followers_55_more"),
        "connect": _to_bool_flag(row.get("connect")),
        "reply": _to_bool_flag(row.get("reply")),
        "send": _to_bool_flag(row.get("send")),
        "creator_id": audit_id,
        "creation_time": utc_now,
        "last_modifier_id": audit_id,
        "last_modification_time": utc_now,
    }


class CreatorIngestionService:
    """Persist creator snapshots into MySQL."""

    def __init__(self) -> None:
        self.default_operator_id = "00000000-0000-0000-0000-000000000000"

    async def ingest(
        self, request: CreatorIngestionRequest, session: AsyncSession
    ) -> CreatorIngestionResult:
        rows = [row.model_dump() for row in request.rows]
        if not rows:
            raise ValueError("rows cannot be empty")

        operator_id = request.operator_id or self.default_operator_id
        audit_id = _normalize_uuid_text(operator_id)
        utc_now = datetime.utcnow()
        crawl_date = date.today()
        task_id = None
        if request.options:
            task_id = _clean_text(request.options.task_id)

        creator_ids: Set[str] = set()
        inserted = 0

        for row in rows:
            payload = _prepare_creator_payload(row)
            if not payload:
                logger.warning("Skip creator row without platform_creator_id")
                continue

            skip_upsert = _to_bool_flag(row.get("skip_creator_upsert"))
            if skip_upsert is None:
                skip_upsert = _to_bool_flag(row.get("skipCreatorUpsert"))
            skip_upsert = bool(skip_upsert)
            if not skip_upsert:
                payload = dict(payload)
                payload.update(
                    {
                        "creator_id": audit_id,
                        "creation_time": utc_now,
                        "last_modifier_id": audit_id,
                        "last_modification_time": utc_now,
                    }
                )
                await self._upsert_creator(session, payload)
                creator_ids.add(payload["platform_creator_id"])
                base_payload = payload
            else:
                base_payload = payload
                logger.info(
                    "Skip creator upsert for sparse row",
                    platform_creator_id=payload.get("platform_creator_id"),
                )

            crawl_payload = _build_crawl_log_payload(
                row,
                base_payload,
                audit_id,
                utc_now,
                crawl_date,
                task_id,
            )
            session.add(CreatorCrawlLogs(**crawl_payload))
            inserted += 1

        logger.info(
            "Creator ingestion completed",
            source=request.source,
            rows=len(rows),
            inserted=inserted,
            creators=len(creator_ids),
        )
        return CreatorIngestionResult(inserted=inserted, creators=len(creator_ids))

    async def _upsert_creator(
        self, session: AsyncSession, payload: Dict[str, Any]
    ) -> None:
        stmt = select(Creators).where(Creators.id == payload["id"])
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            for key, value in payload.items():
                if key in {"creator_id", "creation_time"}:
                    continue
                setattr(existing, key, value)
            return

        session.add(Creators(**payload))


creator_ingestion_service = CreatorIngestionService()
