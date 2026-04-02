from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Iterable
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.services.contract_reminder_service import (
    ContractReminderEffectiveRule,
    ContractReminderService,
)
from apps.portal_seller_open_api.services.normalization import (
    clean_text,
    normalize_identifier,
)
from apps.portal_seller_open_api.services.task_dispatch_service import (
    SellerRpaTaskDispatchService,
)
from apps.portal_seller_open_api.services.task_notification_service import (
    SellerRpaTaskNotificationService,
)
from apps.portal_seller_open_api.services.task_slot_dispatch_service import (
    SellerRpaTaskSingleSlotDispatchService,
)
from core_base import get_logger
from shared_seller_application_services.current_user_info import CurrentUserInfo
from shared_domain.models.infound import (
    SellerTkContractMonitorLogs,
    SellerTkSampleCrawlLogs,
    SellerTkSamples,
    SellerTkRpaTaskPlans,
)


class SellerRpaTaskOrchestrationService:
    RULE_OVERDUE_URGE = "OVERDUE_URGE"
    RULE_CONTENT_PENDING_3D = "CONTENT_PENDING_3D"
    RULE_CONTENT_COMPLETE_3D = "CONTENT_COMPLETE_3D"
    ACTIVE_CONTRACT_RULE_CODES = {
        RULE_OVERDUE_URGE,
        RULE_CONTENT_PENDING_3D,
        RULE_CONTENT_COMPLETE_3D,
    }

    def __init__(self, db_session: AsyncSession, settings: Settings) -> None:
        self.db_session = db_session
        self.settings = settings
        self.logger = get_logger(self.__class__.__name__)
        self.notification_service = SellerRpaTaskNotificationService(settings)
        self.dispatch_service = SellerRpaTaskDispatchService(settings)
        self.slot_dispatch_service = SellerRpaTaskSingleSlotDispatchService(
            db_session, settings
        )

    async def prepare_outreach_follow_up_tasks(
        self,
        current_user: CurrentUserInfo,
        *,
        task_id: str,
        shop_id: str,
        shop_region_code: str,
        search_keyword: str | None,
        message: str | None,
        first_message: str | None,
        second_message: str | None,
        creators: Iterable[Any],
    ) -> list[SellerTkRpaTaskPlans]:
        parent_plan = await self._get_parent_task_plan(current_user.user_id, task_id, "OUTREACH")
        if parent_plan is None:
            self.logger.warn("建联派生任务失败：未找到父任务计划", task_id=task_id)
            return []

        parent_payload = self._coerce_payload(parent_plan.task_payload)
        parent_task_node = self._ensure_record(parent_payload.get("task"))
        parent_input_node = self._ensure_record(parent_payload.get("input"))
        parent_payload_node = self._ensure_record(parent_input_node.get("payload"))
        root_task_id = (
            clean_text(parent_task_node.get("rootTaskId"))
            or clean_text(parent_payload_node.get("rootTaskId"))
            or parent_plan.id
        )
        now = datetime.utcnow()
        created_plans: list[SellerTkRpaTaskPlans] = []
        chat_message = clean_text(message) or clean_text(first_message)

        for raw_creator in creators:
            creator_record = self._ensure_record(raw_creator)
            platform_creator_id = normalize_identifier(
                creator_record.get("platform_creator_id") or creator_record.get("creator_id")
            )
            if not platform_creator_id:
                continue

            creator_name = (
                clean_text(creator_record.get("creator_name"))
                or clean_text(creator_record.get("platform_creator_display_name"))
                or platform_creator_id
            )
            base_context = {
                "platform": "tiktok",
                "platform_creator_id": platform_creator_id,
                "platform_creator_display_name": creator_name,
                "platform_creator_username": creator_name,
                "search_keyword": clean_text(search_keyword),
                "search_keywords": clean_text(search_keyword),
                "connect": 1,
                "reply": 0,
                "send": 1,
            }

            detail_payload = self._build_base_child_payload(
                parent_payload=parent_payload,
                task_id=self._stable_task_id(
                    f"seller-rpa:detail:{root_task_id}:{platform_creator_id}"
                ),
                task_type="CREATOR_DETAIL",
                task_name=f"达人详情-{creator_name}",
                shop_id=shop_id,
                shop_region_code=shop_region_code,
                parent_task_id=parent_plan.id,
                root_task_id=root_task_id,
                chain_stage="DETAIL",
                scheduled_time=now,
            )
            detail_input_node = self._mutable_record(detail_payload, "input")
            detail_input_payload = self._mutable_record(detail_input_node, "payload")
            detail_input_payload.update(
                {
                    "creatorId": platform_creator_id,
                    "context": base_context,
                }
            )
            self._copy_optional_value(
                parent_payload_node,
                detail_input_payload,
                "creatorDetailScript",
                "script",
            )
            self._copy_optional_value(
                parent_payload_node,
                detail_input_payload,
                "creatorDetailScriptPath",
                "scriptPath",
            )
            detail_plan = await self._create_child_task_plan(
                current_user=current_user,
                task_id=detail_payload["task"]["taskId"],
                task_type="CREATOR_DETAIL",
                task_payload=detail_payload,
                scheduled_time=now,
            )
            if detail_plan is not None:
                created_plans.append(detail_plan)

            if not chat_message:
                continue

            chat_payload = self._build_base_child_payload(
                parent_payload=parent_payload,
                task_id=self._stable_task_id(
                    f"seller-rpa:chat:{root_task_id}:{platform_creator_id}"
                ),
                task_type="CHAT",
                task_name=f"聊天任务-{creator_name}",
                shop_id=shop_id,
                shop_region_code=shop_region_code,
                parent_task_id=parent_plan.id,
                root_task_id=root_task_id,
                chain_stage="CHAT",
                scheduled_time=now,
            )
            chat_input_node = self._mutable_record(chat_payload, "input")
            chat_input_payload = self._mutable_record(chat_input_node, "payload")
            chat_input_payload.update(
                {
                    "creatorId": platform_creator_id,
                    "creatorName": creator_name,
                    "message": chat_message,
                    "firstMessage": clean_text(first_message) or chat_message,
                    "secondMessage": clean_text(second_message),
                    "businessMode": "chat",
                    "recipients": [
                        {
                            "creatorId": platform_creator_id,
                            "creatorName": creator_name,
                            "message": chat_message,
                        }
                    ],
                }
            )
            self._copy_optional_value(parent_payload_node, chat_input_payload, "chatScript", "script")
            self._copy_optional_value(
                parent_payload_node, chat_input_payload, "chatScriptPath", "scriptPath"
            )
            chat_plan = await self._create_child_task_plan(
                current_user=current_user,
                task_id=chat_payload["task"]["taskId"],
                task_type="CHAT",
                task_payload=chat_payload,
                scheduled_time=now,
            )
            if chat_plan is not None:
                created_plans.append(chat_plan)

        return created_plans

    async def prepare_sample_follow_up_tasks(
        self,
        current_user: CurrentUserInfo,
        *,
        task_id: str,
        shop_id: str,
        shop_region_code: str,
        rows: Iterable[Any],
    ) -> list[SellerTkRpaTaskPlans]:
        parent_plan = await self._get_parent_task_plan(
            current_user.user_id, task_id, "SAMPLE_MONITOR"
        )
        if parent_plan is None:
            self.logger.warn("样品监控派生催单失败：未找到父任务计划", task_id=task_id)
            return []

        active_rule_bindings = await self._get_active_contract_rules(
            current_user.user_id, shop_id
        )
        if not active_rule_bindings:
            return []

        parent_payload = self._coerce_payload(parent_plan.task_payload)
        parent_task_node = self._ensure_record(parent_payload.get("task"))
        parent_input_node = self._ensure_record(parent_payload.get("input"))
        parent_payload_node = self._ensure_record(parent_input_node.get("payload"))
        root_task_id = (
            clean_text(parent_task_node.get("rootTaskId"))
            or clean_text(parent_payload_node.get("rootTaskId"))
            or parent_plan.id
        )
        now = datetime.utcnow()
        created_plans: list[SellerTkRpaTaskPlans] = []

        for raw_row in rows:
            row_context = self._build_contract_row_context(raw_row)
            if row_context is None:
                continue

            monitor = await self._load_contract_monitor_state(
                current_user,
                shop_id=shop_id,
                row_context=row_context,
                updated_at=now,
            )
            if monitor is None:
                continue

            due_rule_bindings = self._select_due_contract_rules(
                monitor, active_rule_bindings, now
            )
            if not due_rule_bindings:
                continue

            creator_name = clean_text(monitor.get("creator_name")) or str(
                monitor["platform_creator_id"]
            )
            days_overdue = self._calculate_days_overdue(monitor.get("expired_in_ms"))
            status_anchor = clean_text(monitor.get("status_anchor")) or str(
                monitor["current_status"]
            )

            for binding in due_rule_bindings:
                rule = binding.rule
                task_id_seed = (
                    f"seller-rpa:urge:{root_task_id}:{rule.code}:{status_anchor}:{monitor['platform_product_id']}:{monitor['platform_creator_id']}"
                )
                child_task_id = self._stable_task_id(task_id_seed)
                existing_plan = await self._find_task_plan(child_task_id)
                if existing_plan is not None:
                    continue

                message = (
                    clean_text(binding.message_template)
                    or clean_text(rule.remark)
                    or clean_text(rule.name)
                    or rule.code
                )
                self.db_session.add(
                    SellerTkContractMonitorLogs(
                        user_id=current_user.user_id,
                        shop_id=shop_id,
                        rule_code=rule.code,
                        platform_creator_id=str(monitor["platform_creator_id"]),
                        message=message or "",
                        creator_id=current_user.user_id,
                        creation_time=now,
                        last_modifier_id=current_user.user_id,
                        last_modification_time=now,
                    )
                )

                urge_payload = self._build_base_child_payload(
                    parent_payload=parent_payload,
                    task_id=child_task_id,
                    task_type="URGE_CHAT",
                    task_name=f"催单私信-{creator_name}",
                    shop_id=shop_id,
                    shop_region_code=shop_region_code,
                    parent_task_id=parent_plan.id,
                    root_task_id=root_task_id,
                    chain_stage="URGE_CHAT",
                    scheduled_time=now,
                )
                urge_input_node = self._mutable_record(urge_payload, "input")
                urge_input_payload = self._mutable_record(urge_input_node, "payload")
                urge_input_payload.update(
                    {
                        "creatorId": monitor["platform_creator_id"],
                        "creatorName": creator_name,
                        "taskType": "URGE_CHAT",
                        "businessMode": "urge",
                        "ruleId": str(rule.id),
                        "ruleCode": rule.code,
                        "ruleName": clean_text(rule.name),
                        "ruleDescription": clean_text(rule.description),
                        "ruleRemark": clean_text(rule.remark),
                        "message": message,
                        "firstMessage": message,
                        "secondMessage": message,
                        "recipients": [
                            {
                                "creatorId": monitor["platform_creator_id"],
                                "creatorName": creator_name,
                                "sampleId": monitor.get("sample_request_id"),
                                "productId": monitor["platform_product_id"],
                                "orderStatus": monitor["current_status"],
                                "daysOverdue": days_overdue,
                                "message": message,
                            }
                        ],
                    }
                )
                self._copy_optional_value(parent_payload_node, urge_input_payload, "urgeScript", "script")
                self._copy_optional_value(
                    parent_payload_node, urge_input_payload, "urgeScriptPath", "scriptPath"
                )
                urge_plan = await self._create_child_task_plan(
                    current_user=current_user,
                    task_id=child_task_id,
                    task_type="URGE_CHAT",
                    task_payload=urge_payload,
                    scheduled_time=now,
                )
                if urge_plan is not None:
                    created_plans.append(urge_plan)

        return created_plans

    async def dispatch_task_plans(self, task_plans: Iterable[SellerTkRpaTaskPlans]) -> None:
        for task_plan in task_plans:
            try:
                if task_plan.scheduled_time <= datetime.utcnow():
                    await self.slot_dispatch_service.dispatch_if_slot_available(
                        task_plan,
                        payload={},
                    )
                    continue

                await self.dispatch_service.schedule_task_plan(task_plan)
            except Exception:
                self.logger.error(
                    "派生任务投递失败",
                    task_id=task_plan.id,
                    task_type=task_plan.task_type,
                    exc_info=True,
                )

    async def _get_parent_task_plan(
        self,
        user_id: str,
        task_id: str,
        task_type: str,
    ) -> SellerTkRpaTaskPlans | None:
        stmt = select(SellerTkRpaTaskPlans).where(
            SellerTkRpaTaskPlans.user_id == user_id,
            SellerTkRpaTaskPlans.id == task_id,
            SellerTkRpaTaskPlans.task_type == task_type,
        )
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_task_plan(self, task_id: str) -> SellerTkRpaTaskPlans | None:
        stmt = select(SellerTkRpaTaskPlans).where(SellerTkRpaTaskPlans.id == task_id)
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_active_contract_rules(
        self,
        user_id: str,
        shop_id: str,
    ) -> list[ContractReminderEffectiveRule]:
        service = ContractReminderService(self.db_session)
        bindings = await service.load_active_rule_bindings(user_id, shop_id)
        return [
            binding for binding in bindings if binding.rule.code in self.ACTIVE_CONTRACT_RULE_CODES
        ]

    async def _load_contract_monitor_state(
        self,
        current_user: CurrentUserInfo,
        *,
        shop_id: str,
        row_context: dict[str, Any],
        updated_at: datetime,
    ) -> dict[str, Any] | None:
        platform_product_id = normalize_identifier(row_context.get("platform_product_id"))
        platform_creator_id = normalize_identifier(row_context.get("platform_creator_id"))
        current_status = clean_text(row_context.get("current_status"))
        if not platform_product_id or not platform_creator_id or not current_status:
            return None

        sample_stmt = select(SellerTkSamples).where(
            SellerTkSamples.user_id == current_user.user_id,
            SellerTkSamples.shop_id == shop_id,
            SellerTkSamples.platform_product_id == platform_product_id,
            SellerTkSamples.platform_creator_id == platform_creator_id,
        )
        sample_result = await self.db_session.execute(sample_stmt)
        try:
            sample = sample_result.scalar_one_or_none()
        finally:
            sample_result.close()
        if sample is None:
            return None

        previous_status: str | None = None
        status_entered_at = updated_at
        last_crawled_at = sample.last_modification_time or updated_at
        if (
            current_status in {"content_pending", "completed"}
            and self._contract_status_to_sample_status(current_status) is not None
        ):
            history_result = await self.db_session.execute(
                select(SellerTkSampleCrawlLogs)
                .where(SellerTkSampleCrawlLogs.sample_id == sample.id)
                .order_by(
                    SellerTkSampleCrawlLogs.creation_time.desc(),
                    SellerTkSampleCrawlLogs.id.desc(),
                )
            )
            try:
                history_rows = history_result.scalars().all()
            finally:
                history_result.close()
            if history_rows:
                last_crawled_at = history_rows[0].creation_time or last_crawled_at
                status_entered_at, previous_status = self._resolve_contract_status_window(
                    history_rows,
                    expected_status=current_status,
                    fallback_time=last_crawled_at,
                )

        days_overdue = self._calculate_days_overdue(row_context.get("expired_in_ms"))
        if current_status == "overdue":
            previous_status = "content_pending"

        status_anchor = (
            f"{current_status}:{days_overdue}"
            if current_status == "overdue"
            else f"{current_status}:{status_entered_at.isoformat()}"
        )
        return {
            "sample_id": sample.id,
            "platform_product_id": platform_product_id,
            "platform_creator_id": platform_creator_id,
            "sample_request_id": normalize_identifier(row_context.get("sample_request_id")),
            "creator_name": clean_text(row_context.get("creator_name"))
            or clean_text(sample.platform_creator_display_name),
            "current_status": current_status,
            "previous_status": previous_status,
            "status_entered_at": status_entered_at,
            "last_crawled_at": last_crawled_at,
            "expired_in_ms": row_context.get("expired_in_ms"),
            "expired_in_text": clean_text(row_context.get("expired_in_text")),
            "status_anchor": status_anchor,
        }

    async def _create_child_task_plan(
        self,
        *,
        current_user: CurrentUserInfo,
        task_id: str,
        task_type: str,
        task_payload: dict[str, Any],
        scheduled_time: datetime,
    ) -> SellerTkRpaTaskPlans | None:
        existing = await self._find_task_plan(task_id)
        if existing is not None:
            return None

        task_plan = SellerTkRpaTaskPlans(
            id=task_id,
            user_id=current_user.user_id,
            task_type=task_type,
            task_payload=task_payload,
            status="PENDING",
            scheduled_time=scheduled_time,
            start_time=None,
            end_time=None,
            heartbeat_at=None,
            error_msg=None,
            creator_id=current_user.user_id,
            creation_time=scheduled_time,
            last_modifier_id=current_user.user_id,
            last_modification_time=scheduled_time,
        )
        self.db_session.add(task_plan)
        return task_plan

    def _build_base_child_payload(
        self,
        *,
        parent_payload: dict[str, Any],
        task_id: str,
        task_type: str,
        task_name: str,
        shop_id: str,
        shop_region_code: str,
        parent_task_id: str,
        root_task_id: str,
        chain_stage: str,
        scheduled_time: datetime,
    ) -> dict[str, Any]:
        parent_task_node = self._ensure_record(parent_payload.get("task"))
        parent_input_node = self._ensure_record(parent_payload.get("input"))
        parent_session_node = self._ensure_record(parent_input_node.get("session"))
        parent_report_node = self._ensure_record(parent_input_node.get("report"))
        parent_executor_node = self._ensure_record(parent_payload.get("executor"))

        return {
            "task": {
                "taskId": task_id,
                "taskType": task_type,
                "taskName": task_name,
                "taskStatus": "PENDING",
                "parentTaskId": parent_task_id,
                "rootTaskId": root_task_id,
                "chainStage": chain_stage,
                "shopId": shop_id,
                "shopRegionCode": shop_region_code,
                "scheduledTime": scheduled_time.isoformat(),
            },
            "input": {
                "session": deepcopy(parent_session_node),
                "payload": {
                    "taskId": task_id,
                    "taskType": task_type,
                    "taskName": task_name,
                    "shopId": shop_id,
                    "shopRegionCode": shop_region_code,
                    "scheduledTime": scheduled_time.isoformat(),
                    "parentTaskId": parent_task_id,
                    "rootTaskId": root_task_id,
                    "chainStage": chain_stage,
                },
                "report": deepcopy(parent_report_node),
            },
            "executor": deepcopy(parent_executor_node),
        }

    @staticmethod
    def _stable_task_id(seed: str) -> str:
        return str(uuid5(NAMESPACE_URL, seed)).upper()

    @staticmethod
    def _coerce_payload(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return deepcopy(value)
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return {}
            try:
                parsed = json.loads(normalized)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
        return {}

    @staticmethod
    def _ensure_record(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return deepcopy(value)
        model_dump = getattr(value, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                return deepcopy(dumped)
        to_dict = getattr(value, "dict", None)
        if callable(to_dict):
            dumped = to_dict()
            if isinstance(dumped, dict):
                return deepcopy(dumped)
        return {}

    @staticmethod
    def _mutable_record(container: dict[str, Any], key: str) -> dict[str, Any]:
        existing = container.get(key)
        if isinstance(existing, dict):
            return existing
        container[key] = {}
        return container[key]

    @staticmethod
    def _copy_optional_value(
        source: dict[str, Any],
        target: dict[str, Any],
        source_key: str,
        target_key: str,
    ) -> None:
        value = source.get(source_key)
        if value not in (None, "", [], {}):
            target[target_key] = deepcopy(value)

    @staticmethod
    def _normalize_sample_status_label(value: str | None) -> str:
        normalized = (clean_text(value) or "").lower()
        mapping = {
            "to review": "to_review",
            "ready to ship": "ready_to_ship",
            "shipped": "shipped",
            "in progress": "in_progress",
            "content pending": "content_pending",
            "completed": "completed",
        }
        return mapping.get(normalized, normalized.replace(" ", "_"))

    def _normalize_contract_status(self, row: dict[str, Any]) -> str | None:
        normalized_status = self._normalize_sample_status_label(
            clean_text(row.get("status")) or clean_text(row.get("tab"))
        )
        if not normalized_status:
            return None

        if normalized_status == "content_pending":
            days_overdue = self._calculate_days_overdue(row.get("expired_in_ms"))
            if days_overdue and days_overdue > 0:
                return "overdue"

        return normalized_status

    def _build_contract_row_context(self, raw_row: Any) -> dict[str, Any] | None:
        row = self._ensure_record(raw_row)
        platform_product_id = normalize_identifier(row.get("product_id"))
        platform_creator_id = normalize_identifier(row.get("creator_id"))
        if not platform_product_id or not platform_creator_id:
            return None

        current_status = self._normalize_contract_status(row)
        if not current_status:
            return None

        return {
            "platform_product_id": platform_product_id,
            "platform_creator_id": platform_creator_id,
            "sample_request_id": normalize_identifier(row.get("sample_request_id")),
            "creator_name": clean_text(row.get("creator_name")),
            "current_status": current_status,
            "expired_in_ms": row.get("expired_in_ms"),
            "expired_in_text": row.get("expired_in_text"),
        }

    def _select_due_contract_rules(
        self,
        monitor: dict[str, Any],
        rules: Iterable[ContractReminderEffectiveRule],
        now: datetime,
    ) -> list[ContractReminderEffectiveRule]:
        due_rules: list[ContractReminderEffectiveRule] = []
        current_status = clean_text(monitor.get("current_status"))
        status_entered_at = monitor.get("status_entered_at") or now
        days_overdue = self._calculate_days_overdue(monitor.get("expired_in_ms"))

        for binding in rules:
            rule = binding.rule
            if rule.code == self.RULE_OVERDUE_URGE:
                if current_status == "overdue" and days_overdue == 1:
                    due_rules.append(binding)
                continue

            if rule.code == self.RULE_CONTENT_PENDING_3D:
                if (
                    current_status == "content_pending"
                    and status_entered_at + timedelta(days=3) <= now
                ):
                    due_rules.append(binding)
                continue

            if rule.code == self.RULE_CONTENT_COMPLETE_3D:
                if current_status == "completed" and status_entered_at + timedelta(days=3) <= now:
                    due_rules.append(binding)

        return due_rules

    def _resolve_contract_status_window(
        self,
        history_rows: list[SellerTkSampleCrawlLogs],
        *,
        expected_status: str,
        fallback_time: datetime,
    ) -> tuple[datetime, str | None]:
        status_entered_at = fallback_time
        previous_status: str | None = None
        for row in history_rows:
            status = self._sample_status_to_contract_status(row.status)
            if not status:
                continue
            if status == expected_status:
                status_entered_at = row.creation_time or status_entered_at
                continue
            previous_status = status
            break
        return status_entered_at, previous_status

    @staticmethod
    def _calculate_days_overdue(value: Any) -> int | None:
        try:
            milliseconds = int(value)
        except (TypeError, ValueError):
            return None
        if milliseconds >= 0:
            return 0
        return max(int(abs(milliseconds) // 86_400_000), 0)

    @staticmethod
    def _contract_status_to_sample_status(value: str | None) -> int | None:
        mapping = {
            "to_review": 1,
            "ready_to_ship": 2,
            "shipped": 3,
            "content_pending": 4,
            "overdue": 4,
            "completed": 5,
            "cancelled": 6,
        }
        return mapping.get(clean_text(value))

    @staticmethod
    def _sample_status_to_contract_status(value: Any) -> str | None:
        mapping = {
            1: "to_review",
            2: "ready_to_ship",
            3: "shipped",
            4: "content_pending",
            5: "completed",
            6: "cancelled",
        }
        try:
            return mapping.get(int(value))
        except (TypeError, ValueError):
            return None
