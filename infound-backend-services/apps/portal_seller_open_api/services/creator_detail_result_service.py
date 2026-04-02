from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.models.creator_detail_result import (
    CreatorDetailContextItem,
    CreatorDetailDataItem,
    CreatorDetailResultIngestionRequest,
    CreatorDetailResultIngestionResult,
)
from apps.portal_seller_open_api.models.entities import CurrentUserInfo
from apps.portal_seller_open_api.services.normalization import (
    clean_text,
    generate_uppercase_uuid,
    normalize_bool_flag,
    normalize_decimal,
    normalize_identifier,
    normalize_int,
    normalize_ratio_decimal,
    normalize_region_code,
    normalize_utc_date,
    normalize_utc_datetime,
)
from shared_domain.models.infound import (
    CreatorCrawlLogs,
    Creators,
    SellerTkShops,
)


class CreatorDetailResultIngestionService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def ingest(
        self,
        current_user: CurrentUserInfo,
        payload: CreatorDetailResultIngestionRequest,
    ) -> CreatorDetailResultIngestionResult:
        task_id = normalize_identifier(payload.task_id)
        if not task_id:
            raise ValueError("task_id is required")

        shop = await self._get_shop(current_user.user_id, payload.shop_id)
        if shop is None:
            raise ValueError("shop_id does not belong to current user")

        detail = payload.detail
        context = payload.context or CreatorDetailContextItem()
        platform = (clean_text(payload.platform) or clean_text(context.platform) or "tiktok").lower()
        platform_creator_id = normalize_identifier(
            context.platform_creator_id or detail.creator_id
        )
        if not platform_creator_id:
            raise ValueError("platform_creator_id is required")

        creator_display_name = (
            clean_text(context.platform_creator_display_name)
            or clean_text(detail.creator_name)
            or platform_creator_id
        )
        creator_username = (
            clean_text(context.platform_creator_username)
            or creator_display_name
            or platform_creator_id
        )

        utc_now = datetime.utcnow()
        collected_at = normalize_utc_datetime(detail.collected_at_utc) or utc_now
        creator_values = self._build_creator_values(
            payload=payload,
            context=context,
            detail=detail,
            platform=platform,
            platform_creator_id=platform_creator_id,
            creator_display_name=creator_display_name,
            creator_username=creator_username,
            current_user=current_user,
            utc_now=utc_now,
        )

        creator_record = await self._find_creator(platform, platform_creator_id)
        if creator_record is None:
            creator_record = Creators(
                id=generate_uppercase_uuid(),
                **creator_values,
            )
            self.db_session.add(creator_record)
        else:
            self._assign_model_values(
                creator_record,
                creator_values,
                skip_fields={"creator_id", "creation_time"},
            )

        crawl_log = CreatorCrawlLogs(
            id=generate_uppercase_uuid(),
            crawl_date=normalize_utc_date(collected_at) or utc_now.date(),
            platform=platform,
            platform_creator_id=platform_creator_id,
            platform_creator_display_name=creator_display_name,
            platform_creator_username=creator_username,
            email=creator_values.get("email"),
            whatsapp=creator_values.get("whatsapp"),
            introduction=creator_values.get("introduction"),
            region=creator_values.get("region"),
            currency=creator_values.get("currency"),
            categories=creator_values.get("categories"),
            chat_url=creator_values.get("chat_url"),
            search_keywords=creator_values.get("search_keywords"),
            brand_name=creator_values.get("brand_name"),
            followers=creator_values.get("followers"),
            top_brands=creator_values.get("top_brands"),
            sales_revenue=creator_values.get("sales_revenue"),
            sales_units_sold=creator_values.get("sales_units_sold"),
            sales_gpm=creator_values.get("sales_gpm"),
            sales_revenue_per_buyer=creator_values.get("sales_revenue_per_buyer"),
            gmv_per_sales_channel=creator_values.get("gmv_per_sales_channel"),
            gmv_by_product_category=creator_values.get("gmv_by_product_category"),
            avg_commission_rate=creator_values.get("avg_commission_rate"),
            collab_products=creator_values.get("collab_products"),
            partnered_brands=creator_values.get("partnered_brands"),
            product_price=creator_values.get("product_price"),
            video_gpm=creator_values.get("video_gpm"),
            videos=creator_values.get("videos"),
            avg_video_views=creator_values.get("avg_video_views"),
            avg_video_engagement_rate=creator_values.get("avg_video_engagement_rate"),
            avg_video_likes=creator_values.get("avg_video_likes"),
            avg_video_comments=creator_values.get("avg_video_comments"),
            avg_video_shares=creator_values.get("avg_video_shares"),
            live_gpm=creator_values.get("live_gpm"),
            live_streams=creator_values.get("live_streams"),
            avg_live_views=creator_values.get("avg_live_views"),
            avg_live_engagement_rate=creator_values.get("avg_live_engagement_rate"),
            avg_live_likes=creator_values.get("avg_live_likes"),
            avg_live_comments=creator_values.get("avg_live_comments"),
            avg_live_shares=creator_values.get("avg_live_shares"),
            followers_male=creator_values.get("followers_male"),
            followers_female=creator_values.get("followers_female"),
            followers_18_24=creator_values.get("followers_18_24"),
            followers_25_34=creator_values.get("followers_25_34"),
            followers_35_44=creator_values.get("followers_35_44"),
            followers_45_54=creator_values.get("followers_45_54"),
            followers_55_more=creator_values.get("followers_55_more"),
            connect=self._to_bit_value(context.connect),
            reply=self._to_bit_value(context.reply),
            send=self._to_bit_value(context.send),
            creator_id=current_user.user_id,
            creation_time=utc_now,
            last_modifier_id=current_user.user_id,
            last_modification_time=utc_now,
        )
        self.db_session.add(crawl_log)
        await self.db_session.commit()

        return CreatorDetailResultIngestionResult(
            task_id=task_id,
            creator_record_id=creator_record.id,
            crawl_log_id=crawl_log.id,
            platform_creator_id=platform_creator_id,
        )

    def _build_creator_values(
        self,
        *,
        payload: CreatorDetailResultIngestionRequest,
        context: CreatorDetailContextItem,
        detail: CreatorDetailDataItem,
        platform: str,
        platform_creator_id: str,
        creator_display_name: str,
        creator_username: str,
        current_user: CurrentUserInfo,
        utc_now: datetime,
    ) -> dict[str, Any]:
        region = (
            normalize_region_code(detail.region)
            or normalize_region_code(payload.shop_region_code)
            or "MX"
        )
        chat_url = self._resolve_chat_url(
            platform=platform,
            explicit_chat_url=context.chat_url,
            platform_creator_id=platform_creator_id,
            region=region,
        )
        follower_gender = self._ensure_mapping(detail.follower_gender)
        follower_age = self._ensure_mapping(detail.follower_age)

        return {
            "platform": platform,
            "platform_creator_id": platform_creator_id,
            "platform_creator_display_name": creator_display_name,
            "platform_creator_username": creator_username,
            "email": clean_text(context.email),
            "whatsapp": clean_text(context.whatsapp),
            "introduction": clean_text(detail.creator_intro),
            "region": region,
            "currency": clean_text(context.currency) or self._currency_for_region(region),
            "categories": self._stringify_text_value(context.categories),
            "chat_url": chat_url,
            "search_keywords": clean_text(context.search_keywords or context.search_keyword),
            "brand_name": clean_text(context.brand_name),
            "followers": normalize_int(detail.creator_followers_count),
            "top_brands": self._truncate_text(self._brands_to_text(detail.brands_list), 255),
            "sales_revenue": self._quantize_decimal(normalize_decimal(detail.gmv), 2),
            "sales_units_sold": normalize_int(detail.items_sold),
            "sales_gpm": self._quantize_decimal(normalize_decimal(detail.gpm), 2),
            "sales_revenue_per_buyer": self._quantize_decimal(
                normalize_decimal(detail.gmv_per_customer), 2
            ),
            "gmv_per_sales_channel": self._summarize_top_ratio_entry(
                detail.gmv_per_sales_channel, max_length=32
            ),
            "gmv_by_product_category": self._summarize_top_ratio_entry(
                detail.gmv_by_product_category, max_length=64
            ),
            "avg_commission_rate": self._quantize_decimal(
                normalize_ratio_decimal(detail.avg_commission_rate), 4
            ),
            "collab_products": normalize_int(detail.products),
            "partnered_brands": normalize_int(detail.brand_collaborations),
            "product_price": self._truncate_text(clean_text(detail.product_price), 64),
            "video_gpm": self._quantize_decimal(normalize_decimal(detail.video_gpm), 2),
            "videos": normalize_int(detail.videos_count),
            "avg_video_views": normalize_int(detail.avg_video_views),
            "avg_video_engagement_rate": self._quantize_decimal(
                normalize_ratio_decimal(detail.avg_video_engagement), 4
            ),
            "avg_video_likes": normalize_int(detail.avg_video_likes),
            "avg_video_comments": normalize_int(detail.avg_video_comments),
            "avg_video_shares": normalize_int(detail.avg_video_shares),
            "live_gpm": self._quantize_decimal(normalize_decimal(detail.live_gpm), 2),
            "live_streams": normalize_int(detail.live_streams),
            "avg_live_views": normalize_int(detail.avg_live_views),
            "avg_live_engagement_rate": self._quantize_decimal(
                normalize_ratio_decimal(detail.avg_live_engagement), 4
            ),
            "avg_live_likes": normalize_int(detail.avg_live_likes),
            "avg_live_comments": normalize_int(detail.avg_live_comments),
            "avg_live_shares": normalize_int(detail.avg_live_shares),
            "followers_male": self._quantize_decimal(
                self._extract_ratio_value(follower_gender, ("male", "men", "man")), 4
            ),
            "followers_female": self._quantize_decimal(
                self._extract_ratio_value(follower_gender, ("female", "women", "woman")), 4
            ),
            "followers_18_24": self._quantize_decimal(
                self._extract_ratio_value(follower_age, ("18-24", "18 - 24")), 4
            ),
            "followers_25_34": self._quantize_decimal(
                self._extract_ratio_value(follower_age, ("25-34", "25 - 34")), 4
            ),
            "followers_35_44": self._quantize_decimal(
                self._extract_ratio_value(follower_age, ("35-44", "35 - 44")), 4
            ),
            "followers_45_54": self._quantize_decimal(
                self._extract_ratio_value(follower_age, ("45-54", "45 - 54")), 4
            ),
            "followers_55_more": self._quantize_decimal(
                self._extract_ratio_value(follower_age, ("55+", "55 +", "55_more")), 4
            ),
            "creator_id": current_user.user_id,
            "creation_time": utc_now,
            "last_modifier_id": current_user.user_id,
            "last_modification_time": utc_now,
        }

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

    async def _find_creator(self, platform: str, platform_creator_id: str) -> Creators | None:
        stmt = select(Creators).where(
            Creators.platform == platform,
            Creators.platform_creator_id == platform_creator_id,
        )
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()

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

    def _ensure_mapping(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                loaded = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return loaded if isinstance(loaded, dict) else {}
        return {}

    def _extract_ratio_value(
        self,
        mapping: dict[str, Any],
        aliases: Iterable[str],
    ) -> Decimal | None:
        normalized_aliases = [self._normalize_key(alias) for alias in aliases]
        for key, value in mapping.items():
            normalized_key = self._normalize_key(key)
            if normalized_key in normalized_aliases:
                return normalize_ratio_decimal(value)
        return None

    def _summarize_top_ratio_entry(self, value: Any, *, max_length: int) -> str | None:
        mapping = self._ensure_mapping(value)
        if not mapping:
            return None

        best_label: str | None = None
        best_ratio: Decimal | None = None
        for key, raw in mapping.items():
            ratio = normalize_ratio_decimal(raw)
            if ratio is None:
                continue
            if best_ratio is None or ratio > best_ratio:
                best_label = clean_text(key)
                best_ratio = ratio

        if not best_label or best_ratio is None:
            return None
        summary = f"{best_label}:{best_ratio.normalize()}"
        return self._truncate_text(summary, max_length)

    def _brands_to_text(self, value: Any) -> str | None:
        if isinstance(value, list):
            items = [clean_text(item) for item in value]
            items = [item for item in items if item]
            return ", ".join(items[:10]) if items else None
        return clean_text(value)

    def _stringify_text_value(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, list):
            items = [clean_text(item) for item in value]
            items = [item for item in items if item]
            return ", ".join(items) if items else None
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return clean_text(value)

    def _truncate_text(self, value: str | None, max_length: int) -> str | None:
        if value is None:
            return None
        return value[:max_length]

    def _quantize_decimal(self, value: Decimal | None, scale: int) -> Decimal | None:
        if value is None:
            return None
        quant = Decimal("1").scaleb(-scale)
        return value.quantize(quant)

    def _resolve_chat_url(
        self,
        *,
        platform: str,
        explicit_chat_url: Any,
        platform_creator_id: str,
        region: str | None,
    ) -> str | None:
        chat_url = clean_text(explicit_chat_url)
        if chat_url:
            return chat_url

        normalized_platform = (platform or "").strip().lower()
        normalized_region = normalize_region_code(region)
        if normalized_platform != "tiktok" or not platform_creator_id or not normalized_region:
            return None

        return (
            "https://affiliate.tiktok.com/seller/im?"
            f"creator_id={quote(platform_creator_id, safe='')}"
            f"&shop_region={quote(normalized_region, safe='')}"
        )

    def _normalize_key(self, value: Any) -> str:
        return str(value or "").strip().lower().replace(" ", "").replace("_", "")

    def _currency_for_region(self, region: str | None) -> str | None:
        normalized = (region or "").strip().upper()
        if normalized in {"FR", "ES", "EU"}:
            return "EU"
        if normalized in {"MX", "MEX"}:
            return "MXN"
        if normalized in {"VN"}:
            return "VND"
        return None

    def _to_bit_value(self, value: Any) -> int | None:
        normalized = normalize_bool_flag(value)
        return int(normalized) if normalized is not None else None
