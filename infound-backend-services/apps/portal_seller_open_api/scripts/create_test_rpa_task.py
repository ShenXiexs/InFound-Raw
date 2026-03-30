from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import and_, select

from apps.portal_seller_open_api.core.config import Settings
from apps.portal_seller_open_api.services.normalization import generate_uppercase_uuid
from apps.portal_seller_open_api.services.task_slot_dispatch_service import (
    SellerRpaTaskSingleSlotDispatchService,
)
from core_base import SettingsFactory, get_logger
from shared_domain import DatabaseManager
from shared_domain.models.infound import SellerTkRpaTaskPlans, SellerTkShops


LOGGER = get_logger("create_test_rpa_task")
DEFAULT_SAMPLE_TABS = ["to_review", "ready_to_ship", "shipped", "in_progress", "completed"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="创建本地联调用的单条 Seller RPA 测试任务")
    parser.add_argument(
        "--task-type",
        required=True,
        choices=["CHAT", "CREATOR_DETAIL", "SAMPLE_MONITOR", "URGE_CHAT"],
        help="测试任务类型",
    )
    parser.add_argument("--shop-id", required=True, help="seller_tk_shops.id")
    parser.add_argument("--user-id", help="可选，显式指定 user_id；默认从店铺查出")
    parser.add_argument("--task-name", help="可选，自定义任务名")
    parser.add_argument("--creator-id", help="CHAT / URGE_CHAT / CREATOR_DETAIL 必填")
    parser.add_argument("--creator-name", default="", help="CHAT / URGE_CHAT / CREATOR_DETAIL 可选")
    parser.add_argument("--message", default="", help="CHAT / URGE_CHAT 必填，发送消息内容")
    parser.add_argument("--second-message", default="", help="CHAT / URGE_CHAT 可选，第二条消息")
    parser.add_argument("--search-keyword", default="", help="CREATOR_DETAIL 可选，搜索关键词")
    parser.add_argument("--rule-code", default="OVERDUE_URGE", help="URGE_CHAT 可选，默认 OVERDUE_URGE")
    parser.add_argument("--sample-id", default="", help="URGE_CHAT 可选，样品申请 id")
    parser.add_argument("--product-id", default="", help="URGE_CHAT 可选，商品 id")
    parser.add_argument("--order-status", default="overdue", help="URGE_CHAT 可选，样品当前状态")
    parser.add_argument("--days-overdue", type=int, default=0, help="URGE_CHAT 可选，超期天数")
    parser.add_argument(
        "--tabs",
        default=",".join(DEFAULT_SAMPLE_TABS),
        help="SAMPLE_MONITOR tab 列表，逗号分隔",
    )
    return parser.parse_args()


def _build_session_node(shop: SellerTkShops) -> dict:
    session_node = {
        "region": str(shop.shop_region_code or "").strip().upper(),
        "headless": False,
    }
    platform_shop_id = str(shop.platform_shop_code or "").strip()
    if platform_shop_id:
        session_node["loginStatePath"] = (
            f"%userData%/tk/{shop.user_id}/{shop.id}/{platform_shop_id}.json"
        )
    return session_node


def _build_base_payload(
    *,
    task_id: str,
    task_type: str,
    task_name: str,
    shop: SellerTkShops,
    scheduled_time: datetime,
) -> dict:
    payload = {
        "task": {
            "taskId": task_id,
            "taskType": task_type,
            "taskName": task_name,
            "taskStatus": "PENDING",
            "parentTaskId": "",
            "rootTaskId": task_id,
            "chainStage": task_type,
            "shopId": shop.id,
            "shopRegionCode": str(shop.shop_region_code or "").strip().upper(),
            "scheduledTime": scheduled_time.isoformat(),
        },
        "input": {
            "session": _build_session_node(shop),
            "payload": {
                "taskId": task_id,
                "taskType": task_type,
                "taskName": task_name,
                "shopId": shop.id,
                "shopRegionCode": str(shop.shop_region_code or "").strip().upper(),
                "scheduledTime": scheduled_time.isoformat(),
                "parentTaskId": "",
                "rootTaskId": task_id,
                "chainStage": task_type,
            },
            "report": {},
        },
        "executor": {
            "host": "frontend.desktop",
            "dispatchMode": "user_notification",
            "transport": "rabbitmq_web_stomp",
            "authMode": "jwt",
        },
    }
    return payload


def _split_tabs(raw_tabs: str) -> list[str]:
    items = [str(item or "").strip() for item in str(raw_tabs or "").split(",")]
    return [item for item in items if item]


async def main() -> int:
    args = parse_args()
    settings = SettingsFactory.initialize(
        settings_class=Settings,
        config_dir=Path(__file__).resolve().parents[1] / "configs",
    )
    DatabaseManager.initialize(settings.mysql)

    task_type = str(args.task_type or "").strip().upper()
    utc_now = datetime.now(UTC).replace(tzinfo=None)
    task_id = generate_uppercase_uuid()

    try:
        async with DatabaseManager.get_session() as session:
            shop_stmt = select(SellerTkShops).where(
                and_(
                    SellerTkShops.id == str(args.shop_id).strip(),
                    SellerTkShops.deleted == 0,
                )
            ).limit(1)
            shop_result = await session.execute(shop_stmt)
            try:
                shop = shop_result.scalar_one_or_none()
            finally:
                shop_result.close()

            if shop is None:
                raise ValueError(f"shop not found: {args.shop_id}")

            user_id = str(args.user_id or shop.user_id or "").strip()
            if not user_id:
                raise ValueError("user_id is empty")
            if user_id != str(shop.user_id or "").strip():
                raise ValueError("user_id does not match shop owner")

            task_name = str(args.task_name or "").strip()
            if not task_name:
                default_name = {
                    "CHAT": "本地聊天发送测试",
                    "CREATOR_DETAIL": "本地达人详情测试",
                    "SAMPLE_MONITOR": "本地样品爬取测试",
                    "URGE_CHAT": "本地催单聊天测试",
                }
                task_name = default_name.get(task_type, f"本地任务测试-{task_type}")

            task_payload = _build_base_payload(
                task_id=task_id,
                task_type=task_type,
                task_name=task_name,
                shop=shop,
                scheduled_time=utc_now,
            )
            input_payload = task_payload["input"]["payload"]

            if task_type in {"CHAT", "URGE_CHAT"}:
                creator_id = str(args.creator_id or "").strip()
                message = str(args.message or "").strip()
                creator_name = str(args.creator_name or "").strip() or creator_id
                if not creator_id:
                    raise ValueError(f"--creator-id is required for {task_type}")
                if not message:
                    raise ValueError(f"--message is required for {task_type}")
                recipient = {
                    "creatorId": creator_id,
                    "creatorName": creator_name,
                    "message": message,
                }
                if task_type == "URGE_CHAT":
                    sample_id = str(args.sample_id or "").strip()
                    product_id = str(args.product_id or "").strip()
                    order_status = str(args.order_status or "").strip()
                    if sample_id:
                        recipient["sampleId"] = sample_id
                    if product_id:
                        recipient["productId"] = product_id
                    if order_status:
                        recipient["orderStatus"] = order_status
                    if int(args.days_overdue or 0) > 0:
                        recipient["daysOverdue"] = int(args.days_overdue)

                input_payload.update(
                    {
                        "creatorId": creator_id,
                        "creatorName": creator_name,
                        "message": message,
                        "firstMessage": message,
                        "secondMessage": str(args.second_message or "").strip(),
                        "businessMode": "urge" if task_type == "URGE_CHAT" else "chat",
                        "ruleCode": str(args.rule_code or "").strip().upper()
                        if task_type == "URGE_CHAT"
                        else None,
                        "recipients": [recipient],
                    }
                )
            elif task_type == "CREATOR_DETAIL":
                creator_id = str(args.creator_id or "").strip()
                creator_name = str(args.creator_name or "").strip() or creator_id
                if not creator_id:
                    raise ValueError("--creator-id is required for CREATOR_DETAIL")
                input_payload.update(
                    {
                        "creatorId": creator_id,
                        "context": {
                            "platform": "tiktok",
                            "platformCreatorId": creator_id,
                            "platformCreatorDisplayName": creator_name,
                            "platformCreatorUsername": creator_name,
                            "searchKeyword": str(args.search_keyword or "").strip(),
                            "searchKeywords": str(args.search_keyword or "").strip(),
                            "connect": 1,
                            "reply": 0,
                            "send": 1,
                        },
                    }
                )
            elif task_type == "SAMPLE_MONITOR":
                input_payload["tabs"] = _split_tabs(args.tabs) or DEFAULT_SAMPLE_TABS
            else:
                raise ValueError(f"unsupported task_type: {task_type}")

            task_plan = SellerTkRpaTaskPlans(
                id=task_id,
                user_id=user_id,
                task_type=task_type,
                task_payload=task_payload,
                status="PENDING",
                scheduled_time=utc_now,
                start_time=None,
                end_time=None,
                heartbeat_at=None,
                error_msg=None,
                creator_id=user_id,
                creation_time=utc_now,
                last_modifier_id=user_id,
                last_modification_time=utc_now,
            )
            session.add(task_plan)
            await session.commit()

            dispatch_service = SellerRpaTaskSingleSlotDispatchService(session, settings)
            dispatch_result = await dispatch_service.dispatch_if_slot_available(task_plan)

            LOGGER.info(
                "测试任务已创建",
                task_id=task_id,
                task_type=task_type,
                shop_id=shop.id,
                user_id=user_id,
                dispatched=dispatch_result.dispatched,
                slot_busy=dispatch_result.slot_busy,
                reason=dispatch_result.reason,
            )
            print(f"task_id={task_id}")
            print(f"task_type={task_type}")
            print(f"shop_id={shop.id}")
            print(f"user_id={user_id}")
            print(f"dispatched={dispatch_result.dispatched}")
            print(f"slot_busy={dispatch_result.slot_busy}")
            print(f"reason={dispatch_result.reason or ''}")
        return 0
    finally:
        await DatabaseManager.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
