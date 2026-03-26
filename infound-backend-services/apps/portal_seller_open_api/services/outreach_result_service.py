from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.models.entities import CurrentUserInfo
from apps.portal_seller_open_api.models.outreach_result import (
    OutreachResultIngestionRequest,
    OutreachResultIngestionResult,
)
from apps.portal_seller_open_api.services.normalization import (
    clean_text,
    duration_seconds,
    generate_bigint_id,
    normalize_bool_flag,
    normalize_identifier,
    normalize_int,
    normalize_outreach_status,
    normalize_utc_datetime,
)
from shared_domain.models.infound import (
    SellerTkOutreachCreatorCounts,
    SellerTkOutreachSettings,
    SellerTkOutreachTaskLogs,
    SellerTkShops,
)


AVG_COMMISSION_RATE_MAPPING = {
    "less than 20%": 20,
    "less than 15%": 15,
    "less than 10%": 10,
    "less than 5%": 5,
}
CONTENT_TYPE_MAPPING = {
    "video": 1,
    "live": 2,
}
CREATOR_AGENCY_MAPPING = {
    "managed by agency": 1,
    "independent creators": 2,
}
FOLLOWER_GENDER_MAPPING = {
    "female": 1,
    "male": 2,
}
EST_POST_RATE_MAPPING = {
    "ok": 1,
    "good": 2,
    "better": 3,
}


class OutreachResultIngestionService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def ingest(
        self,
        current_user: CurrentUserInfo,
        payload: OutreachResultIngestionRequest,
    ) -> OutreachResultIngestionResult:
        task_id = normalize_identifier(payload.task_id)
        if not task_id:
            raise ValueError("task_id is required")

        shop = await self._get_shop(current_user.user_id, payload.shop_id)
        if shop is None:
            raise ValueError("shop_id does not belong to current user")

        utc_now = datetime.utcnow()
        started_at = normalize_utc_datetime(payload.started_at)
        finished_at = normalize_utc_datetime(payload.finished_at)
        normalized_creators = self._normalize_creators(payload)
        existing_settings = await self._find_settings(task_id)

        real_count = normalize_int(payload.real_count)
        if real_count is None:
            real_count = len(normalized_creators)

        new_count = normalize_int(payload.new_count)
        explicit_new_count = self._explicit_new_count(normalized_creators)
        if new_count is None and explicit_new_count is not None:
            new_count = explicit_new_count

        spend_time = normalize_int(payload.spend_time)
        if spend_time is None:
            spend_time = duration_seconds(started_at, finished_at)

        settings_payload = {
            "id": task_id,
            "user_id": current_user.user_id,
            "shop_id": shop.id,
            "shop_region_code": clean_text(payload.shop_region_code)
            or shop.shop_region_code,
            "task_name": clean_text(payload.task_name) or f"OUTREACH-{task_id[:8]}",
            "task_type": clean_text(payload.task_type) or "OUTREACH",
            "status": normalize_outreach_status(payload.status),
            "creator_id": current_user.user_id,
            "creation_time": utc_now,
            "last_modifier_id": current_user.user_id,
            "last_modification_time": utc_now,
            "real_count": real_count,
            "new_count": new_count,
        }

        optional_values = {
            "duplicate_check_type": normalize_int(payload.duplicate_check_type),
            "duplicate_check_code": clean_text(payload.duplicate_check_code),
            "message_send_strategy": normalize_int(payload.message_send_strategy),
            "message": clean_text(payload.message),
            "search_keywords": clean_text(payload.search_keyword),
            "first_message": clean_text(payload.first_message),
            "second_message": clean_text(payload.second_message),
            "filter_sort_by": normalize_int(payload.filter_sort_by),
            "plan_execute_time": normalize_int(payload.plan_execute_time),
            "expect_count": normalize_int(payload.expect_count),
            "spend_time": spend_time,
            "real_start_at": started_at,
            "real_end_at": finished_at,
        }
        settings_payload.update(
            {key: value for key, value in optional_values.items() if value is not None}
        )
        settings_payload.update(self._build_filter_settings(payload))

        await self._upsert_settings(settings_payload)

        inserted_logs = 0
        updated_creator_counts = 0
        inferred_new_count = 0
        for creator in normalized_creators.values():
            existing_log = await self._find_task_log(task_id, creator["platform_creator_id"])
            if existing_log is not None:
                continue

            self.db_session.add(
                SellerTkOutreachTaskLogs(
                    id=generate_bigint_id(),
                    shop_id=shop.id,
                    task_id=task_id,
                    platform_creator_id=creator["platform_creator_id"],
                    creator_id=current_user.user_id,
                    creation_time=utc_now,
                    last_modifier_id=current_user.user_id,
                    last_modification_time=utc_now,
                )
            )
            inserted_logs += 1

            count_row = await self._find_creator_count(
                shop.id, creator["platform_creator_id"]
            )
            creator_is_new = creator["is_new"]
            if creator_is_new is None:
                creator_is_new = count_row is None
            if creator_is_new:
                inferred_new_count += 1
            if count_row is None:
                self.db_session.add(
                    SellerTkOutreachCreatorCounts(
                        id=generate_bigint_id(),
                        shop_id=shop.id,
                        platform_creator_id=creator["platform_creator_id"],
                        connect_count=1,
                        creator_id=current_user.user_id,
                        creation_time=utc_now,
                        last_modifier_id=current_user.user_id,
                        last_modification_time=utc_now,
                    )
                )
            else:
                count_row.connect_count = int(count_row.connect_count or 0) + 1
                count_row.last_modifier_id = current_user.user_id
                count_row.last_modification_time = utc_now
            updated_creator_counts += 1

        if new_count is None:
            if inserted_logs == 0 and existing_settings is not None:
                new_count = int(existing_settings.new_count or 0)
            else:
                new_count = inferred_new_count
            settings_payload["new_count"] = new_count
            await self._upsert_settings(settings_payload)

        await self.db_session.commit()

        return OutreachResultIngestionResult(
            task_id=task_id,
            inserted_task_logs=inserted_logs,
            updated_creator_counts=updated_creator_counts,
            real_count=real_count,
            new_count=new_count,
        )

    def _normalize_creators(self, payload: OutreachResultIngestionRequest) -> dict[str, dict]:
        creators: dict[str, dict] = {}
        for item in payload.creators:
            platform_creator_id = normalize_identifier(
                item.platform_creator_id or item.creator_id
            )
            if not platform_creator_id:
                continue

            send_flag = normalize_bool_flag(item.send)
            if send_flag is None:
                send_flag = 1
            if send_flag != 1:
                continue

            existing = creators.get(platform_creator_id)
            is_new = normalize_bool_flag(item.is_new) == 1
            send_time = normalize_utc_datetime(item.send_time)
            if existing is None:
                creators[platform_creator_id] = {
                    "platform_creator_id": platform_creator_id,
                    "is_new": is_new if item.is_new is not None else None,
                    "send_time": send_time,
                    "creator_name": clean_text(item.creator_name),
                    "avatar_url": clean_text(item.avatar_url),
                    "category": clean_text(item.category),
                }
            else:
                if item.is_new is not None:
                    existing["is_new"] = bool(existing["is_new"]) or is_new
                existing["send_time"] = existing["send_time"] or send_time
                existing["creator_name"] = existing["creator_name"] or clean_text(
                    item.creator_name
                )
                existing["avatar_url"] = existing["avatar_url"] or clean_text(
                    item.avatar_url
                )
                existing["category"] = existing["category"] or clean_text(item.category)
        return creators

    def _explicit_new_count(self, creators: dict[str, dict]) -> int | None:
        if not creators:
            return 0
        if not any(item["is_new"] is not None for item in creators.values()):
            return None
        return sum(1 for item in creators.values() if item["is_new"])

    def _build_filter_settings(
        self, payload: OutreachResultIngestionRequest
    ) -> dict[str, Any]:
        normalized: dict[str, Any] = {}

        creator_filters = payload.creator_filters
        if creator_filters is not None:
            product_categories = self._normalize_selection_list(
                creator_filters.product_category_selections
            )
            if product_categories is not None:
                normalized["filter_product_categories"] = product_categories

            avg_commission_rate = self._map_option_to_number(
                creator_filters.avg_commission_rate,
                AVG_COMMISSION_RATE_MAPPING,
            )
            if avg_commission_rate is not None:
                normalized["filter_avg_commission_rate"] = avg_commission_rate

            content_type = self._map_option_to_number(
                creator_filters.content_type,
                CONTENT_TYPE_MAPPING,
            )
            if content_type is not None:
                normalized["filter_content_types"] = content_type

            creator_agency = self._map_option_to_number(
                creator_filters.creator_agency,
                CREATOR_AGENCY_MAPPING,
            )
            if creator_agency is not None:
                normalized["filter_creator_agency"] = creator_agency

            if creator_filters.fast_growing is not None:
                normalized["filter_fast_growth_list"] = (
                    1 if bool(creator_filters.fast_growing) else 0
                )

            if creator_filters.not_invited_in_past_90_days is not None:
                normalized["filter_uninvited_creators_in_90_days"] = (
                    1 if bool(creator_filters.not_invited_in_past_90_days) else 0
                )

        follower_filters = payload.follower_filters
        if follower_filters is not None:
            follower_ages = self._normalize_selection_list(
                follower_filters.follower_age_selections
            )
            if follower_ages is not None:
                normalized["filter_fans_age_range"] = follower_ages

            follower_gender = self._map_option_to_number(
                follower_filters.follower_gender,
                FOLLOWER_GENDER_MAPPING,
            )
            if follower_gender is not None:
                normalized["filter_fans_gender"] = follower_gender

            follower_count_range = self._normalize_range(
                follower_filters.follower_count_min,
                follower_filters.follower_count_max,
            )
            if follower_count_range is not None:
                normalized["filter_fans_count_range"] = follower_count_range

        performance_filters = payload.performance_filters
        if performance_filters is not None:
            gmv_range = self._normalize_selection_list(
                performance_filters.gmv_selections
            )
            if gmv_range is not None:
                normalized["filter_gmv_range"] = gmv_range

            sales_count_range = self._normalize_selection_list(
                performance_filters.items_sold_selections
            )
            if sales_count_range is not None:
                normalized["filter_sales_count_range"] = sales_count_range

            avg_video_views = self._normalize_positive_int(
                performance_filters.average_views_per_video_min
            )
            if avg_video_views is not None:
                normalized["filter_min_avg_video_views"] = avg_video_views

            avg_live_views = self._normalize_positive_int(
                performance_filters.average_viewers_per_live_min
            )
            if avg_live_views is not None:
                normalized["filter_min_avg_live_views"] = avg_live_views

            engagement_rate = self._normalize_positive_int(
                performance_filters.engagement_rate_min_percent
            )
            if engagement_rate is not None:
                normalized["filter_min_engagement_rate"] = engagement_rate

            estimated_publish_rate = self._map_option_to_number(
                performance_filters.est_post_rate,
                EST_POST_RATE_MAPPING,
            )
            if estimated_publish_rate is not None:
                normalized["filter_creator_estimated_publish_rate"] = (
                    estimated_publish_rate
                )

            co_branding = self._normalize_selection_list(
                performance_filters.brand_collaboration_selections
            )
            if co_branding is not None:
                normalized["filter_co_branding"] = co_branding

        return normalized

    @staticmethod
    def _normalize_selection_list(values: Iterable[Any] | None) -> list[str] | None:
        if values is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = clean_text(value)
            if not text:
                continue
            dedupe_key = text.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized.append(text)
        return normalized or None

    @staticmethod
    def _map_option_to_number(
        value: Any,
        mapping: dict[str, int],
    ) -> int | None:
        text = (clean_text(value) or "").lower()
        if not text or text == "all":
            return None
        return mapping.get(text)

    @staticmethod
    def _normalize_range(min_value: Any, max_value: Any) -> dict[str, int] | None:
        normalized_min = normalize_int(min_value)
        normalized_max = normalize_int(max_value)
        range_payload: dict[str, int] = {}
        if normalized_min is not None:
            range_payload["min"] = normalized_min
        if normalized_max is not None:
            range_payload["max"] = normalized_max
        return range_payload or None

    @staticmethod
    def _normalize_positive_int(value: Any) -> int | None:
        normalized = normalize_int(value)
        if normalized is None or normalized <= 0:
            return None
        return normalized

    async def _get_shop(self, user_id: str, shop_id: str) -> SellerTkShops | None:
        normalized_shop_id = normalize_identifier(shop_id)
        if not normalized_shop_id:
            return None
        stmt = select(SellerTkShops).where(
            SellerTkShops.id == normalized_shop_id,
            SellerTkShops.user_id == user_id,
            (SellerTkShops.deleted.is_(None)) | (SellerTkShops.deleted == 0),
        )
        return (await self.db_session.execute(stmt)).scalar_one_or_none()

    async def _upsert_settings(self, payload: dict) -> None:
        stmt = select(SellerTkOutreachSettings).where(
            SellerTkOutreachSettings.id == payload["id"]
        )
        existing = (await self.db_session.execute(stmt)).scalar_one_or_none()
        if existing is None:
            self.db_session.add(SellerTkOutreachSettings(**payload))
            return

        for key, value in payload.items():
            if key in {"creator_id", "creation_time"}:
                continue
            setattr(existing, key, value)

    async def _find_settings(self, task_id: str) -> SellerTkOutreachSettings | None:
        stmt = select(SellerTkOutreachSettings).where(
            SellerTkOutreachSettings.id == task_id
        )
        return (await self.db_session.execute(stmt)).scalar_one_or_none()

    async def _find_task_log(
        self, task_id: str, platform_creator_id: str
    ) -> SellerTkOutreachTaskLogs | None:
        stmt = select(SellerTkOutreachTaskLogs).where(
            SellerTkOutreachTaskLogs.task_id == task_id,
            SellerTkOutreachTaskLogs.platform_creator_id == platform_creator_id,
        )
        return (await self.db_session.execute(stmt)).scalar_one_or_none()

    async def _find_creator_count(
        self, shop_id: str, platform_creator_id: str
    ) -> SellerTkOutreachCreatorCounts | None:
        stmt = select(SellerTkOutreachCreatorCounts).where(
            SellerTkOutreachCreatorCounts.shop_id == shop_id,
            SellerTkOutreachCreatorCounts.platform_creator_id == platform_creator_id,
        )
        return (await self.db_session.execute(stmt)).scalar_one_or_none()
