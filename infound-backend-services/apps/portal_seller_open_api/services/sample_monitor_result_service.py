from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.models.entities import CurrentUserInfo
from apps.portal_seller_open_api.models.sample_monitor_result import (
    SampleMonitorResultIngestionRequest,
    SampleMonitorResultIngestionResult,
    SampleMonitorRowItem,
)
from apps.portal_seller_open_api.services.normalization import (
    clean_text,
    generate_uppercase_uuid,
    normalize_bool_flag,
    normalize_identifier,
    normalize_int,
    normalize_ratio_decimal,
    normalize_region_code,
    normalize_utc_datetime,
)
from apps.portal_seller_open_api.services.task_orchestration_service import (
    SellerRpaTaskOrchestrationService,
)
from shared_domain.models.infound import (
    SellerTkProducts,
    SellerTkSampleContentCrawlLogs,
    SellerTkSampleContents,
    SellerTkSampleCrawlLogs,
    SellerTkSamples,
    SellerTkShops,
)


class SampleMonitorResultIngestionService:
    def __init__(self, db_session: AsyncSession, settings: Settings) -> None:
        self.db_session = db_session
        self.task_orchestration_service = SellerRpaTaskOrchestrationService(
            db_session, settings
        )

    async def ingest(
        self,
        current_user: CurrentUserInfo,
        payload: SampleMonitorResultIngestionRequest,
    ) -> SampleMonitorResultIngestionResult:
        task_id = normalize_identifier(payload.task_id)
        if not task_id:
            raise ValueError("task_id is required")

        shop = await self._get_shop(current_user.user_id, payload.shop_id)
        if shop is None:
            raise ValueError("shop_id does not belong to current user")

        utc_now = datetime.utcnow()
        rows = self._flatten_rows(payload)
        if not rows:
            return SampleMonitorResultIngestionResult(
                task_id=task_id,
                rows_processed=0,
                product_upserts=0,
                sample_upserts=0,
                sample_content_upserts=0,
                sample_crawl_logs_inserted=0,
                sample_content_crawl_logs_inserted=0,
            )

        product_keys: set[tuple[str, str, str]] = set()
        sample_keys: set[tuple[str, str, str, str | None]] = set()
        sample_content_keys: set[tuple[str, str, str, str | None, str | None, str | None, str | None]] = set()
        sample_crawl_logs_inserted = 0
        sample_content_crawl_logs_inserted = 0

        for row in rows:
            platform_product_id = normalize_identifier(row.product_id)
            if not platform_product_id:
                continue

            platform_creator_id = normalize_identifier(row.creator_id)
            creator_name = clean_text(row.creator_name)
            available_sample_count = normalize_int(row.available_sample_count)
            product_key = (current_user.user_id, shop.id, platform_product_id)
            product_keys.add(product_key)
            await self._upsert_product(
                current_user=current_user,
                shop_id=shop.id,
                row=row,
                utc_now=utc_now,
            )

            sample = await self._upsert_sample(
                current_user=current_user,
                shop_id=shop.id,
                shop_region_code=clean_text(payload.shop_region_code) or shop.shop_region_code,
                row=row,
                utc_now=utc_now,
            )
            sample_key = (current_user.user_id, shop.id, platform_product_id, platform_creator_id)
            sample_keys.add(sample_key)

            self.db_session.add(
                SellerTkSampleCrawlLogs(
                    sample_id=sample.id,
                    platform_product_id=platform_product_id,
                    crawl_date=self._resolve_crawl_date(row, utc_now),
                    product_sku=clean_text(row.sku_id),
                    available_sample_count=available_sample_count,
                    is_uncooperative=self._to_bit_value(None),
                    is_unapprovable=self._to_bit_value(None),
                    status=self._normalize_sample_status(row.status or row.tab),
                    request_time_remaining=clean_text(row.expired_in_text),
                    platform_creator_id=platform_creator_id,
                    platform_creator_username=creator_name,
                    platform_creator_display_name=creator_name,
                    post_rate=self._quantize_decimal(
                        normalize_ratio_decimal(row.commission_rate), 4
                    ),
                    content_summary=self._parse_content_summary(row.content_summary),
                    creator_id=current_user.user_id,
                    creation_time=utc_now,
                    last_modifier_id=current_user.user_id,
                    last_modification_time=utc_now,
                )
            )
            sample_crawl_logs_inserted += 1

            content_summary = self._parse_content_summary(row.content_summary)
            content_items = (
                content_summary.get("items", [])
                if isinstance(content_summary, dict)
                else []
            )
            for item in content_items:
                sample_content = await self._upsert_sample_content(
                    current_user=current_user,
                    shop_id=shop.id,
                    row=row,
                    item=item,
                    utc_now=utc_now,
                )
                sample_content_key = (
                    current_user.user_id,
                    shop.id,
                    platform_product_id,
                    platform_creator_id,
                    clean_text(item.get("content_title")),
                    clean_text(item.get("content_time")),
                    self._normalize_content_type(item.get("content_type")),
                )
                sample_content_keys.add(sample_content_key)

                self.db_session.add(
                    SellerTkSampleContentCrawlLogs(
                        id=generate_uppercase_uuid(),
                        smaple_content_id=str(sample_content.id),
                        platform_product_id=platform_product_id,
                        crawl_date=self._resolve_crawl_date(row, utc_now),
                        type=self._normalize_content_type(item.get("content_type")),
                        platform_creator_id=platform_creator_id,
                        platform_creator_display_name=creator_name,
                        platform_creator_username=creator_name,
                        platform_detail_url=None,
                        promotion_name=clean_text(item.get("content_title")),
                        promotion_time=clean_text(item.get("content_time")),
                        promotion_view_count=normalize_int(item.get("content_view")),
                        promotion_like_count=normalize_int(item.get("content_like")),
                        promotion_comment_count=normalize_int(item.get("comment_num")),
                        promotion_order_count=normalize_int(item.get("content_order")),
                        promotion_order_total_amount=None,
                        creator_id=current_user.user_id,
                        creation_time=utc_now,
                        last_modifier_id=current_user.user_id,
                        last_modification_time=utc_now,
                    )
                )
                sample_content_crawl_logs_inserted += 1

        derived_task_plans = await self.task_orchestration_service.prepare_sample_follow_up_tasks(
            current_user,
            task_id=task_id,
            shop_id=shop.id,
            shop_region_code=clean_text(payload.shop_region_code) or shop.shop_region_code,
            rows=rows,
        )
        await self.db_session.commit()
        await self.task_orchestration_service.dispatch_task_plans(derived_task_plans)

        return SampleMonitorResultIngestionResult(
            task_id=task_id,
            rows_processed=len(rows),
            product_upserts=len(product_keys),
            sample_upserts=len(sample_keys),
            sample_content_upserts=len(sample_content_keys),
            sample_crawl_logs_inserted=sample_crawl_logs_inserted,
            sample_content_crawl_logs_inserted=sample_content_crawl_logs_inserted,
        )

    def _flatten_rows(self, payload: SampleMonitorResultIngestionRequest) -> list[SampleMonitorRowItem]:
        rows: list[SampleMonitorRowItem] = []
        for key in ("to_review", "ready_to_ship", "shipped", "in_progress", "completed"):
            tab_result = getattr(payload.result, key, None)
            if tab_result is None:
                continue
            rows.extend(tab_result.rows or [])
        return rows

    async def _get_shop(self, user_id: str, shop_id: str | None) -> SellerTkShops | None:
        normalized_shop_id = normalize_identifier(shop_id)
        if not normalized_shop_id:
            return None
        stmt = select(SellerTkShops).where(
            SellerTkShops.user_id == user_id,
            SellerTkShops.id == normalized_shop_id,
        )
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()

    async def _upsert_product(
        self,
        *,
        current_user: CurrentUserInfo,
        shop_id: str,
        row: SampleMonitorRowItem,
        utc_now: datetime,
    ) -> SellerTkProducts:
        platform_product_id = normalize_identifier(row.product_id)
        stmt = (
            select(SellerTkProducts)
            .where(
                SellerTkProducts.user_id == current_user.user_id,
                SellerTkProducts.shop_id == shop_id,
                SellerTkProducts.platform_product_id == platform_product_id,
            )
            .order_by(
                SellerTkProducts.last_modification_time.desc(),
                SellerTkProducts.id.desc(),
            )
        )
        result = await self.db_session.execute(stmt)
        existing = result.scalars().first()
        values = {
            "user_id": current_user.user_id,
            "shop_id": shop_id,
            "platform_product_id": platform_product_id,
            "thumbnail": clean_text(row.sku_image),
            "product_name": clean_text(row.product_name),
            "creator_rate": self._quantize_decimal(
                normalize_ratio_decimal(row.commission_rate), 2
            ),
            "product_sku": clean_text(row.sku_id),
            "stock": normalize_int(row.sku_stock),
            "creator_id": current_user.user_id,
            "creation_time": utc_now,
            "last_modifier_id": current_user.user_id,
            "last_modification_time": utc_now,
        }
        if existing is None:
            product = SellerTkProducts(
                id=generate_uppercase_uuid(),
                **values,
            )
            self.db_session.add(product)
            return product

        self._assign_model_values(
            existing,
            values,
            skip_fields={"creator_id", "creation_time"},
        )
        return existing

    async def _upsert_sample(
        self,
        *,
        current_user: CurrentUserInfo,
        shop_id: str,
        shop_region_code: str,
        row: SampleMonitorRowItem,
        utc_now: datetime,
    ) -> SellerTkSamples:
        platform_product_id = normalize_identifier(row.product_id)
        platform_creator_id = normalize_identifier(row.creator_id)
        stmt = (
            select(SellerTkSamples)
            .where(
                SellerTkSamples.user_id == current_user.user_id,
                SellerTkSamples.shop_id == shop_id,
                SellerTkSamples.platform_product_id == platform_product_id,
                self._eq_or_is_null(SellerTkSamples.platform_creator_id, platform_creator_id),
            )
            .order_by(
                SellerTkSamples.last_modification_time.desc(),
                SellerTkSamples.id.desc(),
            )
        )
        result = await self.db_session.execute(stmt)
        existing = result.scalars().first()
        values = {
            "user_id": current_user.user_id,
            "shop_id": shop_id,
            "platform_product_id": platform_product_id,
            "product_sku": clean_text(row.sku_id),
            "available_sample_count": normalize_int(row.available_sample_count),
            "is_uncooperative": self._to_bit_value(None),
            "is_unapprovable": self._to_bit_value(None),
            "status": self._normalize_sample_status(row.status or row.tab),
            "request_time_remaining": clean_text(row.expired_in_text),
            "platform_creator_id": platform_creator_id,
            "platform_creator_username": clean_text(row.creator_name),
            "platform_creator_display_name": clean_text(row.creator_name),
            "post_rate": self._quantize_decimal(
                normalize_ratio_decimal(row.commission_rate), 4
            ),
            "content_summary": self._parse_content_summary(row.content_summary),
            "creator_id": current_user.user_id,
            "creation_time": utc_now,
            "last_modifier_id": current_user.user_id,
            "last_modification_time": utc_now,
        }
        if existing is None:
            sample = SellerTkSamples(
                id=generate_uppercase_uuid(),
                **values,
            )
            self.db_session.add(sample)
            return sample

        self._assign_model_values(
            existing,
            values,
            skip_fields={"creator_id", "creation_time"},
        )
        return existing

    async def _upsert_sample_content(
        self,
        *,
        current_user: CurrentUserInfo,
        shop_id: str,
        row: SampleMonitorRowItem,
        item: dict[str, Any],
        utc_now: datetime,
    ) -> SellerTkSampleContents:
        platform_product_id = normalize_identifier(row.product_id)
        platform_creator_id = normalize_identifier(row.creator_id)
        content_type = self._normalize_content_type(item.get("content_type"))
        promotion_name = clean_text(item.get("content_title"))
        promotion_time = clean_text(item.get("content_time"))
        stmt = (
            select(SellerTkSampleContents)
            .where(
                SellerTkSampleContents.user_id == current_user.user_id,
                SellerTkSampleContents.shop_id == shop_id,
                SellerTkSampleContents.platform_product_id == platform_product_id,
                self._eq_or_is_null(
                    SellerTkSampleContents.platform_creator_id,
                    platform_creator_id,
                ),
                self._eq_or_is_null(SellerTkSampleContents.type, content_type),
                self._eq_or_is_null(
                    SellerTkSampleContents.promotion_name,
                    promotion_name,
                ),
                self._eq_or_is_null(
                    SellerTkSampleContents.promotion_time,
                    promotion_time,
                ),
            )
            .order_by(
                SellerTkSampleContents.last_modification_time.desc(),
                SellerTkSampleContents.id.desc(),
            )
            .limit(1)
        )
        result = await self.db_session.execute(stmt)
        existing = result.scalars().first()

        values = {
            "user_id": current_user.user_id,
            "shop_id": shop_id,
            "platform_product_id": platform_product_id,
            "type": content_type,
            "platform_creator_id": platform_creator_id,
            "platform_creator_display_name": clean_text(row.creator_name),
            "platform_creator_username": clean_text(row.creator_name),
            "platform_detail_url": None,
            "promotion_name": promotion_name,
            "promotion_time": promotion_time,
            "promotion_view_count": normalize_int(item.get("content_view")),
            "promotion_like_count": normalize_int(item.get("content_like")),
            "promotion_comment_count": normalize_int(item.get("comment_num")),
            "promotion_order_count": normalize_int(item.get("content_order")),
            "promotion_order_total_amount": None,
            "creator_id": current_user.user_id,
            "creation_time": utc_now,
            "last_modifier_id": current_user.user_id,
            "last_modification_time": utc_now,
        }
        if existing is None:
            sample_content = SellerTkSampleContents(**values)
            self.db_session.add(sample_content)
            await self.db_session.flush()
            return sample_content

        self._assign_model_values(
            existing,
            values,
            skip_fields={"creator_id", "creation_time"},
        )
        await self.db_session.flush()
        return existing

    def _parse_content_summary(self, value: Any) -> Any:
        if value is None or value == "":
            return None
        if isinstance(value, (dict, list)):
            return value
        text = str(value).strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"count": 0, "items": [], "raw": text}

    def _normalize_sample_status(self, value: Any) -> int | None:
        text = str(value or "").strip().lower().replace("-", " ").replace("_", " ")
        mapping = {
            "to review": 1,
            "ready to review": 1,
            "review": 1,
            "ready to ship": 2,
            "shipped": 3,
            "in progress": 4,
            "content pending": 4,
            "completed": 5,
            "cancelled": 6,
            "canceled": 6,
        }
        return mapping.get(text)

    def _normalize_content_type(self, value: Any) -> str | None:
        text = str(value or "").strip().lower()
        if not text:
            return None
        if text in {"video", "2"}:
            return "1"
        if text in {"live", "1"}:
            return "2"
        return text

    def _resolve_crawl_date(self, row: SampleMonitorRowItem, utc_now: datetime):
        return normalize_utc_datetime(row.crawl_time).date() if normalize_utc_datetime(row.crawl_time) else utc_now.date()

    def _quantize_decimal(self, value: Decimal | None, scale: int) -> Decimal | None:
        if value is None:
            return None
        quant = Decimal("1").scaleb(-scale)
        return value.quantize(quant)

    def _assign_model_values(
        self,
        model: Any,
        values: dict[str, Any],
        *,
        skip_fields: set[str],
    ) -> None:
        for key, value in values.items():
            if key in skip_fields:
                continue
            if value is None:
                continue
            setattr(model, key, value)

    def _to_bit_value(self, value: Any) -> int | None:
        normalized = normalize_bool_flag(value)
        return int(normalized) if normalized is not None else None

    def _eq_or_is_null(self, column: Any, value: Any):
        return column.is_(None) if value is None else column == value
