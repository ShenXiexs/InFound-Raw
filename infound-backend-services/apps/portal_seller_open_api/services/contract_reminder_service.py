from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.models.contract_reminder import (
    ContractReminderLogItem,
    ContractReminderLogListData,
    ContractReminderMonitorItem,
    ContractReminderMonitorListData,
    ContractReminderRuleConfigItem,
    ContractReminderRuleConfigListData,
    ContractReminderRuleConfigUpdateRequest,
)
from apps.portal_seller_open_api.models.entities import CurrentUserInfo
from apps.portal_seller_open_api.services.normalization import (
    clean_text,
    generate_uppercase_uuid,
    normalize_identifier,
)
from shared_domain.models.infound import (
    SellerTkContractMonitorLogs,
    SellerTkContractMonitorRules,
    SellerTkContractMonitors,
    SellerTkSamples,
    SellerTkShops,
)


@dataclass(slots=True)
class ContractReminderEffectiveRule:
    rule: SellerTkContractMonitorRules
    monitor: SellerTkContractMonitors | None
    message_template: str | None
    is_active: bool


class ContractReminderService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def list_rule_configs(
        self,
        current_user: CurrentUserInfo,
        *,
        shop_id: str,
    ) -> ContractReminderRuleConfigListData:
        normalized_shop_id = await self._ensure_owned_shop(current_user.user_id, shop_id)
        effective_rules = await self._load_rule_bindings(
            current_user.user_id, normalized_shop_id
        )
        return ContractReminderRuleConfigListData(
            shopId=normalized_shop_id,
            items=[
                ContractReminderRuleConfigItem(
                    ruleId=effective.rule.id,
                    ruleCode=effective.rule.code,
                    ruleName=effective.rule.name,
                    description=clean_text(effective.rule.description),
                    remark=clean_text(effective.rule.remark),
                    defaultMessage=clean_text(effective.rule.description),
                    messageTemplate=effective.message_template,
                    isActive=effective.is_active,
                    hasOverride=effective.monitor is not None,
                    lastModificationTime=(
                        effective.monitor.last_modification_time
                        if effective.monitor is not None
                        else effective.rule.last_modification_time
                    ),
                )
                for effective in effective_rules
            ],
        )

    async def save_rule_configs(
        self,
        current_user: CurrentUserInfo,
        payload: ContractReminderRuleConfigUpdateRequest,
    ) -> ContractReminderRuleConfigListData:
        normalized_shop_id = await self._ensure_owned_shop(current_user.user_id, payload.shopId)
        now = datetime.utcnow()

        stmt = (
            select(SellerTkContractMonitorRules)
            .where(
                SellerTkContractMonitorRules.code.in_(
                    [
                        str(item.ruleCode).strip().upper()
                        for item in payload.items
                        if clean_text(item.ruleCode)
                    ]
                )
            )
        )
        rule_result = await self.db_session.execute(stmt)
        try:
            rules = {row.code: row for row in rule_result.scalars().all()}
        finally:
            rule_result.close()

        for item in payload.items:
            normalized_rule_code = str(item.ruleCode).strip().upper()
            if normalized_rule_code not in rules:
                raise ValueError(f"unknown ruleCode: {item.ruleCode}")

            existing_stmt = (
                select(SellerTkContractMonitors)
                .where(
                    SellerTkContractMonitors.user_id == current_user.user_id,
                    SellerTkContractMonitors.shop_id == normalized_shop_id,
                    SellerTkContractMonitors.rule_code == normalized_rule_code,
                )
                .order_by(
                    SellerTkContractMonitors.last_modification_time.desc(),
                    SellerTkContractMonitors.id.desc(),
                )
            )
            existing_result = await self.db_session.execute(existing_stmt)
            try:
                existing = existing_result.scalars().first()
            finally:
                existing_result.close()
            message_template = clean_text(item.messageTemplate) or ""

            if existing is None:
                self.db_session.add(
                    SellerTkContractMonitors(
                        id=generate_uppercase_uuid(),
                        user_id=current_user.user_id,
                        shop_id=normalized_shop_id,
                        rule_code=normalized_rule_code,
                        message_template=message_template,
                        is_active=1 if item.isActive else 0,
                        creator_id=current_user.user_id,
                        creation_time=now,
                        last_modifier_id=current_user.user_id,
                        last_modification_time=now,
                    )
                )
                continue

            existing.message_template = message_template
            existing.is_active = 1 if item.isActive else 0
            existing.last_modifier_id = current_user.user_id
            existing.last_modification_time = now

        await self.db_session.commit()
        return await self.list_rule_configs(current_user, shop_id=normalized_shop_id)

    async def list_monitors(
        self,
        current_user: CurrentUserInfo,
        *,
        shop_id: str,
        current_status: str | None,
        page: int,
        page_size: int,
    ) -> ContractReminderMonitorListData:
        normalized_shop_id = await self._ensure_owned_shop(current_user.user_id, shop_id)
        stmt = select(SellerTkSamples).where(
            SellerTkSamples.user_id == current_user.user_id,
            SellerTkSamples.shop_id == normalized_shop_id,
        )
        normalized_status = self._normalize_sample_status_filter(current_status)
        if normalized_status is not None:
            stmt = stmt.where(SellerTkSamples.status == normalized_status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db_session.execute(count_stmt)
        try:
            total = int(count_result.scalar() or 0)
        finally:
            count_result.close()
        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(
                SellerTkSamples.last_modification_time.desc(),
                SellerTkSamples.id.desc(),
            )
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db_session.execute(stmt)
        try:
            rows = result.scalars().all()
        finally:
            result.close()
        return ContractReminderMonitorListData(
            total=total,
            page=page,
            pageSize=page_size,
            items=[
                ContractReminderMonitorItem(
                    id=row.id,
                    platformProductId=row.platform_product_id,
                    platformCreatorId=row.platform_creator_id or "",
                    sampleRequestId=None,
                    creatorName=row.platform_creator_display_name,
                    currentStatus=self._sample_status_to_label(row.status),
                    previousStatus=None,
                    statusEnteredAt=row.last_modification_time,
                    lastCrawledAt=row.last_modification_time,
                    expiredInMs=None,
                    expiredInText=row.request_time_remaining,
                    cycleToken=row.id,
                    lastModificationTime=row.last_modification_time,
                )
                for row in rows
            ],
        )

    async def list_logs(
        self,
        current_user: CurrentUserInfo,
        *,
        shop_id: str,
        rule_code: str | None,
        platform_creator_id: str | None,
        task_plan_id: str | None,
        send_status: str | None,
        page: int,
        page_size: int,
    ) -> ContractReminderLogListData:
        normalized_shop_id = await self._ensure_owned_shop(current_user.user_id, shop_id)
        stmt = select(SellerTkContractMonitorLogs).where(
            SellerTkContractMonitorLogs.user_id == current_user.user_id,
            SellerTkContractMonitorLogs.shop_id == normalized_shop_id,
        )
        normalized_rule_code = clean_text(rule_code)
        if normalized_rule_code:
            stmt = stmt.where(SellerTkContractMonitorLogs.rule_code == normalized_rule_code.upper())
        normalized_creator_id = normalize_identifier(platform_creator_id)
        if normalized_creator_id:
            stmt = stmt.where(
                SellerTkContractMonitorLogs.platform_creator_id == normalized_creator_id
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db_session.execute(count_stmt)
        try:
            total = int(count_result.scalar() or 0)
        finally:
            count_result.close()
        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(
                SellerTkContractMonitorLogs.creation_time.desc(),
                SellerTkContractMonitorLogs.id.desc(),
            )
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db_session.execute(stmt)
        try:
            rows = result.scalars().all()
        finally:
            result.close()
        return ContractReminderLogListData(
            total=total,
            page=page,
            pageSize=page_size,
            items=[
                ContractReminderLogItem(
                    id=row.id,
                    ruleCode=row.rule_code,
                    platformProductId=None,
                    platformCreatorId=row.platform_creator_id,
                    sampleRequestId=None,
                    currentStatus=None,
                    cycleToken=None,
                    taskPlanId=None,
                    message=row.message,
                    triggeredAt=None,
                    sendStatus=None,
                    errorMsg=None,
                    creationTime=row.creation_time,
                )
                for row in rows
            ],
        )

    async def load_active_rule_bindings(
        self,
        user_id: str,
        shop_id: str,
    ) -> list[ContractReminderEffectiveRule]:
        normalized_shop_id = normalize_identifier(shop_id)
        if not normalized_shop_id:
            return []
        return [
            binding
            for binding in await self._load_rule_bindings(user_id, normalized_shop_id)
            if binding.is_active
        ]

    async def _load_rule_bindings(
        self,
        user_id: str,
        shop_id: str,
    ) -> list[ContractReminderEffectiveRule]:
        rule_stmt = select(SellerTkContractMonitorRules).order_by(
            SellerTkContractMonitorRules.id.asc()
        )
        rule_result = await self.db_session.execute(rule_stmt)
        try:
            rules = rule_result.scalars().all()
        finally:
            rule_result.close()

        monitor_stmt = (
            select(SellerTkContractMonitors)
            .where(
                SellerTkContractMonitors.user_id == user_id,
                SellerTkContractMonitors.shop_id == shop_id,
            )
            .order_by(
                SellerTkContractMonitors.last_modification_time.desc(),
                SellerTkContractMonitors.id.desc(),
            )
        )
        monitor_result = await self.db_session.execute(monitor_stmt)
        try:
            monitors: dict[str, SellerTkContractMonitors] = {}
            for row in monitor_result.scalars().all():
                if row.rule_code not in monitors:
                    monitors[row.rule_code] = row
        finally:
            monitor_result.close()

        items: list[ContractReminderEffectiveRule] = []
        for rule in rules:
            monitor = monitors.get(rule.code)
            effective_active = (
                self._bit_to_bool(monitor.is_active)
                if monitor is not None
                else self._bit_to_bool(rule.is_active)
            )
            items.append(
                ContractReminderEffectiveRule(
                    rule=rule,
                    monitor=monitor,
                    message_template=(
                        clean_text(monitor.message_template)
                        if monitor is not None
                        else clean_text(rule.description)
                    ),
                    is_active=effective_active,
                )
            )
        return items

    @staticmethod
    def _normalize_sample_status_filter(value: str | None) -> int | None:
        normalized = (clean_text(value) or "").lower().replace("-", "_").replace(" ", "_")
        if not normalized:
            return None
        mapping = {
            "to_review": 1,
            "ready_to_ship": 2,
            "shipped": 3,
            "in_progress": 4,
            "content_pending": 4,
            "overdue": 4,
            "completed": 5,
            "cancelled": 6,
            "canceled": 6,
        }
        return mapping.get(normalized)

    @staticmethod
    def _sample_status_to_label(value: int | None) -> str:
        mapping = {
            1: "to_review",
            2: "ready_to_ship",
            3: "shipped",
            4: "content_pending",
            5: "completed",
            6: "cancelled",
        }
        return mapping.get(int(value or 0), "unknown")

    @staticmethod
    def _bit_to_bool(value: object) -> bool:
        if value in (None, False, 0):
            return False
        if value is True:
            return True
        if isinstance(value, (bytes, bytearray, memoryview)):
            raw = bytes(value)
            return any(raw)
        try:
            return bool(int(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return bool(value)

    async def _ensure_owned_shop(self, user_id: str, shop_id: str) -> str:
        normalized_shop_id = normalize_identifier(shop_id)
        if not normalized_shop_id:
            raise ValueError("shopId is required")
        stmt = select(SellerTkShops.id).where(
            and_(
                SellerTkShops.id == normalized_shop_id,
                SellerTkShops.user_id == user_id,
                SellerTkShops.deleted == 0,
            )
        )
        result = await self.db_session.execute(stmt)
        try:
            owned_shop = result.scalar_one_or_none()
        finally:
            result.close()
        if not owned_shop:
            raise ValueError("shopId does not belong to current user")
        return normalized_shop_id
