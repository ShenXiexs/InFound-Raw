from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.core.config import Settings
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
    normalize_utc_datetime,
)
from apps.portal_seller_open_api.services.task_orchestration_service import (
    SellerRpaTaskOrchestrationService,
)
from shared_domain.models.infound import (
    IfTkCreators,
    SellerTkOutreachCreatorCounts,
    SellerTkOutreachSettings,
    SellerTkOutreachTaskLogs,
    SellerTkShops,
)
from shared_domain.models.task_plan_extension import TaskStatus


class OutreachResultIngestionService:
    def __init__(self, db_session: AsyncSession, settings: Settings) -> None:
        self.db_session = db_session
        self.task_orchestration_service = SellerRpaTaskOrchestrationService(
            db_session, settings
        )
        self._outreach_task_logs_has_sub_task_id: bool | None = None

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

        utc_now = datetime.now(timezone.utc)
        started_at = normalize_utc_datetime(payload.started_at)
        finished_at = normalize_utc_datetime(payload.finished_at)
        normalized_creators = self._normalize_creators(payload)
        existing_settings = await self._find_settings(task_id)
        if existing_settings is None:
            raise ValueError("outreach settings not found for task_id")
        if (
                str(existing_settings.user_id or "").strip() != current_user.user_id
                or str(existing_settings.shop_id or "").strip() != shop.id
        ):
            raise ValueError("task_id does not belong to current shop")

        message_send_strategy = normalize_int(existing_settings.message_send_strategy)
        brand_names = self._resolve_shop_brand_names(shop)
        normalized_creators = await self._apply_message_send_strategy(
            normalized_creators,
            strategy=message_send_strategy,
            brand_names=brand_names,
        )

        expect_count = normalize_int(existing_settings.expect_count)
        selected_creators = self._limit_creators_by_expect_count(
            normalized_creators, expect_count
        )
        selected_creators_by_id = {
            creator["platform_creator_id"]: creator for creator in selected_creators
        }
        selected_creator_count = len(selected_creators)

        existing_real_count = 0
        if existing_settings.real_count is not None:
            existing_real_count = max(0, int(existing_settings.real_count or 0))
        real_count = min(existing_real_count, selected_creator_count)

        new_count = normalize_int(payload.new_count)
        explicit_new_count = self._explicit_new_count(selected_creators_by_id)
        if new_count is None and explicit_new_count is not None:
            new_count = explicit_new_count

        spend_time = normalize_int(payload.spend_time)
        effective_start_at = started_at
        if effective_start_at is None:
            effective_start_at = existing_settings.real_start_at
        has_selected_creators = selected_creator_count > 0
        if spend_time is None:
            if has_selected_creators:
                spend_time = int(existing_settings.spend_time or 0)
            else:
                spend_time = duration_seconds(effective_start_at, finished_at or utc_now)

        existing_settings.status = (
            TaskStatus.RUNNING.value if has_selected_creators else TaskStatus.COMPLETED.value
        )
        existing_settings.last_modifier_id = current_user.user_id
        existing_settings.last_modification_time = utc_now
        existing_settings.real_count = real_count
        existing_settings.spend_time = spend_time
        existing_settings.real_start_at = effective_start_at
        existing_settings.real_end_at = None if has_selected_creators else (finished_at or utc_now)

        inserted_logs = 0
        updated_creator_counts = 0
        inferred_new_count = 0
        for creator in selected_creators:
            existing_log = await self._find_task_log(task_id, creator["platform_creator_id"])
            if existing_log is not None:
                existing_log.last_modifier_id = current_user.user_id
                existing_log.last_modification_time = utc_now
                continue

            await self._insert_task_log(
                id_=generate_bigint_id(),
                shop_id=shop.id,
                task_id=task_id,
                sub_task_id=SellerRpaTaskOrchestrationService.build_outreach_detail_task_id(
                    task_id,
                    creator["platform_creator_id"],
                ),
                platform_creator_id=creator["platform_creator_id"],
                actor_id=current_user.user_id,
                utc_now=utc_now,
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
            if inserted_logs == 0:
                new_count = int(existing_settings.new_count or 0)
            else:
                new_count = inferred_new_count
        existing_settings.new_count = new_count

        derived_task_plans = []
        if selected_creators:
            derived_task_plans = (
                await self.task_orchestration_service.prepare_outreach_follow_up_tasks_for_creator(
                    current_user,
                    task_id=task_id,
                    shop_id=shop.id,
                    shop_region_code=clean_text(existing_settings.shop_region_code)
                                     or shop.shop_region_code,
                    brand_name=brand_names[0] if brand_names else None,
                    search_keyword=clean_text(existing_settings.search_keywords),
                    message=clean_text(existing_settings.first_message),
                    first_message=clean_text(existing_settings.first_message),
                    second_message=clean_text(existing_settings.second_message),
                    creator=selected_creators[0],
                )
            )
        await self.db_session.commit()
        await self.task_orchestration_service.dispatch_task_plans(derived_task_plans)

        return OutreachResultIngestionResult(
            task_id=task_id,
            inserted_task_logs=inserted_logs,
            updated_creator_counts=updated_creator_counts,
            real_count=real_count,
            new_count=new_count,
        )

    @staticmethod
    def _limit_creators_by_expect_count(
            creators: dict[str, dict],
            expect_count: int | None,
    ) -> list[dict]:
        ordered_creators = list(creators.values())
        if expect_count is None:
            return ordered_creators
        return ordered_creators[: max(0, expect_count)]

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

    async def _apply_message_send_strategy(
            self,
            creators: dict[str, dict],
            *,
            strategy: int | None,
            brand_names: list[str],
    ) -> dict[str, dict]:
        if not creators or strategy != 1 or not brand_names:
            return creators

        existing_creator_ids = await self._find_existing_creator_ids_by_brand(
            creators.keys(),
            brand_names,
        )
        filtered: dict[str, dict] = {}
        for platform_creator_id, creator in creators.items():
            if platform_creator_id in existing_creator_ids:
                continue
            creator_copy = dict(creator)
            creator_copy["is_new"] = True
            filtered[platform_creator_id] = creator_copy
        return filtered

    @staticmethod
    def _resolve_shop_brand_names(shop: SellerTkShops) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in (shop.shop_name, shop.platform_shop_name):
            text = clean_text(value)
            if not text:
                continue
            dedupe_key = text.lower()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized.append(text)
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

    async def _insert_task_log(
            self,
            *,
            id_: int,
            shop_id: str,
            task_id: str,
            sub_task_id: str,
            platform_creator_id: str,
            actor_id: str,
            utc_now: datetime,
    ) -> None:
        params = {
            "id": id_,
            "shop_id": shop_id,
            "task_id": task_id,
            "platform_creator_id": platform_creator_id,
            "creator_id": actor_id,
            "creation_time": utc_now,
            "last_modifier_id": actor_id,
            "last_modification_time": utc_now,
        }
        if await self._has_outreach_task_log_sub_task_id():
            params["sub_task_id"] = sub_task_id
            await self.db_session.execute(
                text(
                    """
                    INSERT INTO seller_tk_outreach_task_logs (
                        id,
                        shop_id,
                        task_id,
                        sub_task_id,
                        platform_creator_id,
                        creator_id,
                        creation_time,
                        last_modifier_id,
                        last_modification_time
                    ) VALUES (
                        :id,
                        :shop_id,
                        :task_id,
                        :sub_task_id,
                        :platform_creator_id,
                        :creator_id,
                        :creation_time,
                        :last_modifier_id,
                        :last_modification_time
                    )
                    """
                ),
                params,
            )
            return

        await self.db_session.execute(
            text(
                """
                INSERT INTO seller_tk_outreach_task_logs (
                    id,
                    shop_id,
                    task_id,
                    platform_creator_id,
                    creator_id,
                    creation_time,
                    last_modifier_id,
                    last_modification_time
                ) VALUES (
                    :id,
                    :shop_id,
                    :task_id,
                    :platform_creator_id,
                    :creator_id,
                    :creation_time,
                    :last_modifier_id,
                    :last_modification_time
                )
                """
            ),
            params,
        )

    async def _has_outreach_task_log_sub_task_id(self) -> bool:
        if self._outreach_task_logs_has_sub_task_id is not None:
            return self._outreach_task_logs_has_sub_task_id

        result = await self.db_session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'seller_tk_outreach_task_logs'
                  AND COLUMN_NAME = 'sub_task_id'
                """
            )
        )
        self._outreach_task_logs_has_sub_task_id = int(result.scalar() or 0) > 0
        return self._outreach_task_logs_has_sub_task_id

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

    async def _find_existing_creator_ids_by_brand(
            self,
            platform_creator_ids: Iterable[str],
            brand_names: Iterable[str],
    ) -> set[str]:
        creator_id_list = [item for item in platform_creator_ids if item]
        brand_name_list = [item for item in brand_names if item]
        if not creator_id_list or not brand_name_list:
            return set()

        stmt = select(IfTkCreators.platform_creator_id).where(
            IfTkCreators.platform_creator_id.in_(creator_id_list),
            IfTkCreators.brand_name.in_(brand_name_list),
        )
        rows = (await self.db_session.execute(stmt)).scalars().all()
        return {str(item).strip() for item in rows if str(item).strip()}
