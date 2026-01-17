from __future__ import annotations

import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.config import get_settings
from common.core.logger import get_logger
from common.models.infound import Campaigns, Products
from apps.portal_inner_open_api.models.campaign import (
    CampaignIngestionRequest,
    CampaignIngestionResult,
    ProductIngestionRequest,
    ProductIngestionResult,
)

settings = get_settings()
logger = get_logger()

PREFERRED_UUID_NODE = 0x2AA7A70856D4


def _generate_uuid() -> str:
    return str(uuid.uuid1(node=PREFERRED_UUID_NODE)).upper()


def _clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _pick_first(row: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key not in row:
            continue
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _safe_region(value: Any, fallback: str) -> str:
    text = _clean_text(value) or fallback
    return text.upper()


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return Decimal(match.group(0))
    except InvalidOperation:
        return None


def _to_percent_string(value: Any) -> Optional[str]:
    text = _clean_text(value)
    if not text:
        return None
    if text.endswith("%"):
        number = _to_decimal(text.replace("%", ""))
        if number is None:
            return None
        try:
            return str((number / Decimal("100")).normalize())
        except Exception:
            return None
    number = _to_decimal(text)
    return str(number.normalize()) if number is not None else None


def _to_period_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = _clean_text(value)
    return [text] if text else None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    text = _clean_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _normalize_price_range(
    min_value: Any, max_value: Any
) -> Tuple[Optional[str], Optional[str]]:
    min_text = _clean_text(min_value)
    max_text = _clean_text(max_value)
    if not min_text and not max_text:
        return None, None
    if min_text and not max_text:
        return min_text, min_text
    if max_text and not min_text:
        return max_text, max_text
    if min_text and max_text and "." not in min_text and "." in max_text and max_text.startswith("0"):
        joined = f"{min_text}{max_text}"
        return joined, joined
    return min_text, max_text


class CampaignIngestionService:
    """Persist campaign/product rows from the crawler into MySQL."""

    def __init__(self) -> None:
        self.default_operator_id = str(
            getattr(settings, "CAMPAIGN_DEFAULT_OPERATOR_ID", None)
            or getattr(settings, "SAMPLE_DEFAULT_OPERATOR_ID", None)
            or "00000000-0000-0000-0000-000000000000"
        )
        self.default_region = str(
            getattr(settings, "CAMPAIGN_DEFAULT_REGION", None) or "MX"
        ).upper()

    async def ingest_campaigns(
        self, request: CampaignIngestionRequest, session: AsyncSession
    ) -> CampaignIngestionResult:
        rows = [row.model_dump() for row in request.rows]
        if not rows:
            raise ValueError("rows cannot be empty")

        operator_id = request.operator_id or self.default_operator_id
        utc_now = datetime.utcnow()

        unique_campaigns: set[str] = set()
        for row in rows:
            payload = self._build_campaign_payload(row, operator_id, utc_now)
            if not payload:
                logger.warning("跳过缺少 platform_campaign_id 的活动行: %s", row)
                continue
            unique_campaigns.add(
                f"{payload.get('platform_campaign_id')}|{payload.get('platform_shop_id') or ''}"
            )
            await self._upsert_campaign(session, payload)

        logger.info(
            "Campaigns ingest completed",
            source=request.source,
            rows=len(rows),
            campaigns=len(unique_campaigns),
        )
        return CampaignIngestionResult(inserted=len(rows), campaigns=len(unique_campaigns))

    async def ingest_products(
        self, request: ProductIngestionRequest, session: AsyncSession
    ) -> ProductIngestionResult:
        rows = [row.model_dump() for row in request.rows]
        if not rows:
            raise ValueError("rows cannot be empty")

        operator_id = request.operator_id or self.default_operator_id
        utc_now = datetime.utcnow()

        unique_products: set[str] = set()
        for row in rows:
            payload = self._build_product_payload(row, operator_id, utc_now)
            if not payload:
                logger.warning("跳过缺少 platform_product_id 的商品行: %s", row)
                continue
            unique_products.add(
                f"{payload.get('platform_campaign_id')}|{payload.get('platform_product_id')}"
            )
            await self._upsert_product(session, payload)

        logger.info(
            "Products ingest completed",
            source=request.source,
            rows=len(rows),
            products=len(unique_products),
        )
        return ProductIngestionResult(inserted=len(rows), products=len(unique_products))

    def _build_campaign_payload(
        self,
        row: Dict[str, Any],
        operator_id: str,
        utc_now: datetime,
    ) -> Optional[Dict[str, Any]]:
        platform_campaign_id = _clean_text(
            _pick_first(row, "platform_campaign_id", "campaign_id")
        )
        if not platform_campaign_id:
            return None
        platform_shop_id = _clean_text(
            _pick_first(row, "platform_shop_id", "shop_code")
        )
        return {
            "platform": _clean_text(_pick_first(row, "platform")) or "tiktok",
            "platform_campaign_id": platform_campaign_id,
            "platform_campaign_name": _clean_text(
                _pick_first(row, "platform_campaign_name", "campaign_name")
            ),
            "region": _safe_region(
                _pick_first(row, "region"),
                self.default_region,
            ),
            "status": _clean_text(_pick_first(row, "status", "campaign_status")),
            "registration_period": _to_period_list(
                _pick_first(row, "registration_period", "campaign_registration_period")
            ),
            "campaign_period": _to_period_list(
                _pick_first(row, "campaign_period")
            ),
            "pending_product_count": _to_int(
                _pick_first(row, "pending_product_count", "campaign_pending_products")
            ),
            "approved_product_count": _to_int(
                _pick_first(row, "approved_product_count", "campaign_approved_products")
            ),
            "date_registered": _parse_datetime(_pick_first(row, "date_registered")),
            "commission_rate": _to_percent_string(_pick_first(row, "commission_rate")),
            "platform_shop_name": _clean_text(
                _pick_first(row, "platform_shop_name", "shop_name")
            ),
            "platform_shop_phone": _clean_text(
                _pick_first(row, "platform_shop_phone", "shop_phone")
            ),
            "platform_shop_id": platform_shop_id,
            "creator_id": operator_id,
            "creation_time": utc_now,
            "last_modifier_id": operator_id,
            "last_modification_time": utc_now,
        }

    def _build_product_payload(
        self,
        row: Dict[str, Any],
        operator_id: str,
        utc_now: datetime,
    ) -> Optional[Dict[str, Any]]:
        platform_campaign_id = _clean_text(
            _pick_first(row, "platform_campaign_id", "campaign_id")
        )
        platform_product_id = _clean_text(
            _pick_first(row, "platform_product_id", "product_id")
        )
        if not platform_campaign_id or not platform_product_id:
            return None
        price_min_raw, price_max_raw = _normalize_price_range(
            _pick_first(row, "sale_price_min"),
            _pick_first(row, "sale_price_max"),
        )
        return {
            "platform": _clean_text(_pick_first(row, "platform")) or "tiktok",
            "platform_campaign_id": platform_campaign_id,
            "platform_product_id": platform_product_id,
            "region": _safe_region(
                _pick_first(row, "region"),
                self.default_region,
            ),
            "platform_shop_name": _clean_text(
                _pick_first(row, "platform_shop_name", "shop_name")
            ),
            "platform_shop_phone": _clean_text(
                _pick_first(row, "platform_shop_phone", "shop_phone")
            ),
            "platform_shop_id": _clean_text(
                _pick_first(row, "platform_shop_id", "shop_code")
            ),
            "thumbnail": _clean_text(_pick_first(row, "thumbnail", "image_link")),
            "product_name": _clean_text(_pick_first(row, "product_name")),
            "product_rating": _to_int(_pick_first(row, "product_rating")),
            "reviews_count": _to_int(_pick_first(row, "reviews_count")),
            "product_sku": _clean_text(_pick_first(row, "product_sku")),
            "stock": _to_int(_pick_first(row, "stock")),
            "available_sample_count": _to_int(
                _pick_first(row, "available_sample_count", "available_sample")
            ),
            "item_sold": _to_int(_pick_first(row, "item_sold", "items_sold")),
            "sale_price_min": _to_decimal(price_min_raw),
            "sale_price_max": _to_decimal(price_max_raw),
            "creator_id": operator_id,
            "creation_time": utc_now,
            "last_modifier_id": operator_id,
            "last_modification_time": utc_now,
        }

    async def _upsert_campaign(
        self, session: AsyncSession, payload: Dict[str, Any]
    ) -> bool:
        def _eq_or_is_null(column, value: Any):
            return column.is_(None) if value is None else column == value

        stmt = select(Campaigns).where(
            Campaigns.platform_campaign_id == payload["platform_campaign_id"],
            _eq_or_is_null(Campaigns.platform_shop_id, payload.get("platform_shop_id")),
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            for key, value in payload.items():
                if key in {"id", "creator_id", "creation_time"}:
                    continue
                setattr(existing, key, value)
            return False

        data = {"id": _generate_uuid(), **payload}
        session.add(Campaigns(**data))
        return True

    async def _upsert_product(
        self, session: AsyncSession, payload: Dict[str, Any]
    ) -> bool:
        stmt = select(Products).where(
            Products.platform_campaign_id == payload["platform_campaign_id"],
            Products.platform_product_id == payload["platform_product_id"],
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            for key, value in payload.items():
                if key in {"id", "creator_id", "creation_time"}:
                    continue
                setattr(existing, key, value)
            return False

        data = {"id": _generate_uuid(), **payload}
        session.add(Products(**data))
        return True


campaign_ingestion_service = CampaignIngestionService()
