from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, asc, desc
from uuid import uuid4
import json

from common.models.infound import OutreachTasks
from common.core.exceptions import ResourceNotFoundError


def _parse_datetime(dt_str: str) -> datetime:
    """Parse datetime string with flexible format (handles non-zero-padded dates)"""
    if not dt_str:
        return None
    # Replace space with T for ISO format
    dt_str = dt_str.replace(" ", "T")
    # Try parsing with fromisoformat first
    try:
        return datetime.fromisoformat(dt_str)
    except ValueError:
        # If that fails, use strptime with flexible format
        return datetime.strptime(dt_str, "%Y-%m-%dT%H:%M")


def _normalize_product_list(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
    else:
        items = [item.strip() for item in str(value).split(",") if item.strip()]
    return items or None


def _list_or_empty(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
        return items
    return [value]


def _format_datetime(value):
    if not value:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


class OutreachTaskService:
    """运营管理-建联任务查询（portal_operation_open_api 专属）"""

    @staticmethod
    def _parse_message_json(message: str) -> dict:
        """安全解析消息 JSON，处理空值和无效 JSON"""
        if not message or not message.strip():
            return {}
        try:
            return json.loads(message)
        except (json.JSONDecodeError, ValueError):
            return {"body": message}

    @staticmethod
    def _calc_running_seconds(task: OutreachTasks) -> int:
        if not task.real_start_at:
            return 0

        if task.real_end_at:
            end_time = task.real_end_at
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            start_time = task.real_start_at
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            return int((end_time - start_time).total_seconds())

        if task.status == "running":
            start_time = task.real_start_at
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            return int((datetime.now(timezone.utc) - start_time).total_seconds())

        return 0

    # =========================
    # 任务一：任务列表
    # =========================
    @staticmethod
    async def get_task_list(
        session: AsyncSession,
        page: int,
        page_size: int,
        status: str | None = None,
        region: str | None = None,
        task_name: str | None = None,
        platform: str | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        plan_start_from: str | None = None,
        plan_start_to: str | None = None,
        plan_end_from: str | None = None,
        plan_end_to: str | None = None,
    ):
        offset = (page - 1) * page_size

        stmt = select(OutreachTasks)
        if status:
            normalized = status.strip().lower()
            if normalized in {"in_progress", "running"}:
                stmt = stmt.where(OutreachTasks.status.in_(["running", "in_progress"]))
            else:
                stmt = stmt.where(OutreachTasks.status == status)
        if region:
            stmt = stmt.where(OutreachTasks.region == region)
        if task_name:
            stmt = stmt.where(OutreachTasks.task_name.like(f"%{task_name}%"))
        if platform:
            stmt = stmt.where(OutreachTasks.platform == platform)

        created_from_dt = _parse_datetime(created_from) if created_from else None
        created_to_dt = _parse_datetime(created_to) if created_to else None
        if created_from_dt:
            stmt = stmt.where(OutreachTasks.creation_time >= created_from_dt)
        if created_to_dt:
            stmt = stmt.where(OutreachTasks.creation_time <= created_to_dt)

        plan_start_from_dt = _parse_datetime(plan_start_from) if plan_start_from else None
        plan_start_to_dt = _parse_datetime(plan_start_to) if plan_start_to else None
        if plan_start_from_dt:
            stmt = stmt.where(OutreachTasks.plan_execute_time >= plan_start_from_dt)
        if plan_start_to_dt:
            stmt = stmt.where(OutreachTasks.plan_execute_time <= plan_start_to_dt)

        plan_end_from_dt = _parse_datetime(plan_end_from) if plan_end_from else None
        plan_end_to_dt = _parse_datetime(plan_end_to) if plan_end_to else None
        if plan_end_from_dt:
            stmt = stmt.where(OutreachTasks.plan_stop_time >= plan_end_from_dt)
        if plan_end_to_dt:
            stmt = stmt.where(OutreachTasks.plan_stop_time <= plan_end_to_dt)

        # total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await session.scalar(count_stmt)

        # list
        sort_map = {
            "created_at": OutreachTasks.creation_time,
            "createdAt": OutreachTasks.creation_time,
            "creation_time": OutreachTasks.creation_time,
            "plan_start_time": OutreachTasks.plan_execute_time,
            "planStartTime": OutreachTasks.plan_execute_time,
            "plan_execute_time": OutreachTasks.plan_execute_time,
            "plan_end_time": OutreachTasks.plan_stop_time,
            "planEndTime": OutreachTasks.plan_stop_time,
            "plan_stop_time": OutreachTasks.plan_stop_time,
            "task_name": OutreachTasks.task_name,
            "taskName": OutreachTasks.task_name,
            "status": OutreachTasks.status,
        }
        sort_column = sort_map.get(sort_by or "", OutreachTasks.creation_time)
        order = (sort_order or "desc").strip().lower()
        order_by = asc(sort_column) if order in {"asc", "ascending"} else desc(sort_column)

        stmt = (
            stmt
            .order_by(order_by)
            .offset(offset)
            .limit(page_size)
        )

        result = await session.execute(stmt)
        tasks = result.scalars().all()

        return {
            "total": total,
            "list": [
                {
                    "taskId": t.id,
                    "taskName": t.task_name,
                    "status": t.status,
                    "platform": t.platform,
                    "region": t.region,
                    "planStartTime": t.plan_execute_time,
                    "planEndTime": t.plan_stop_time,
                    "spendTime": OutreachTaskService._calc_running_seconds(t),
                    "progress": {
                        "current": t.new_creators_real_count or 0,
                        "target": t.new_creators_expect_count or 0,
                    },
                    "createdAt": t.creation_time,
                }
                for t in tasks
            ],
        }

    # =========================
    # 任务二：任务详情
    # =========================
    @staticmethod
    async def get_task_detail(
        session: AsyncSession,
        task_id: str,
    ):
        stmt = select(OutreachTasks).where(OutreachTasks.id == task_id)
        result = await session.execute(stmt)
        t = result.scalar_one_or_none()

        if not t:
            raise ResourceNotFoundError("outreach task")

        return {
            "taskId": t.id,
            "taskName": t.task_name,
            "status": t.status,
            "platform": t.platform,

            "region": t.region,
            "campaignId": t.platform_campaign_id,
            "campaignName": t.platform_campaign_name,
            "brand": t.brand,
            "productId": t.platform_product_id,
            "productName": t.platform_product_name,

            "productList": (
                _list_or_empty(t.product_list)
                if getattr(t, "product_list", None)
                else _list_or_empty(t.platform_product_name)
            ),

            "messageSendStrategy": t.message_send_strategy,

            "searchStrategy": {
                "searchKeywords": t.search_keywords,
                "productCategories": t.product_categories,
                "fansAgeRange": t.fans_age_range,
                "fansGender": t.fans_gender,
                "contentTypes": t.content_types,
                "gmvRange": _list_or_empty(t.gmv_range),
                "salesRange": _list_or_empty(t.sales_range),
                "minFans": t.min_fans,
                "minAvgViews": t.min_avg_views,
                "minEngagementRate": t.min_engagement_rate,
            },

            "messages": {
                "first": OutreachTaskService._parse_message_json(t.first_message),
                "second": OutreachTaskService._parse_message_json(t.second_message),
            },

            "plan": {
                "startTime": t.plan_execute_time,
                "endTime": t.plan_stop_time,
                "targetCreators": t.new_creators_expect_count,
                "maxCreators": t.max_creators,
            },

            "runtime": {
                "spendTime": OutreachTaskService._calc_running_seconds(t),
                "realStartAt": t.real_start_at,
                "realEndAt": t.real_end_at,
                "currentCreators": t.new_creators_real_count,
            },

            "createdAt": t.creation_time,
        }

    # =========================
    # 任务三：创建任务
    # =========================
    @staticmethod
    async def create_task(
        session: AsyncSession,
        payload,
    ):
        """
        创建建联任务
        """
        task_id = str(uuid4()).upper()
        now = datetime.now(timezone.utc)

        # 创建任务对象
        task = OutreachTasks(
            id=task_id,
            platform="tiktok",  # 默认平台
            task_name=payload.task_name,
            creator_id="00000000-0000-0000-0000-000000000000",  # 默认创建人
            creation_time=now,
            last_modifier_id="00000000-0000-0000-0000-000000000000",
            last_modification_time=now,
            platform_campaign_id=payload.campaign_id,
            platform_campaign_name=payload.campaign_name,
            platform_product_id=str(payload.product_id) if payload.product_id else None,
            platform_product_name=payload.product_name,
            region=payload.region,
            brand=payload.brand.name if hasattr(payload.brand, 'name') else str(payload.brand),
            product_list=_normalize_product_list(payload.product_list),
            message_send_strategy=int(payload.brand.only_first),
            task_type="Connect",
            status="not_started",  # 初始状态
            search_keywords=(
                payload.search_strategy.search_keywords or payload.brand.key_word
            ),
            product_categories=payload.search_strategy.product_category,
            fans_age_range=payload.search_strategy.fans_age_range,
            fans_gender=payload.search_strategy.fans_gender,
            content_types=payload.search_strategy.content_type,
            gmv_range=(
                payload.search_strategy.gmv
                if payload.search_strategy.gmv not in (None, [])
                else payload.search_strategy.min_GMV
            ),
            sales_range=(
                payload.search_strategy.sales
                if payload.search_strategy.sales not in (None, [])
                else payload.search_strategy.min_sales
            ),
            min_fans=payload.search_strategy.min_fans,
            min_avg_views=payload.search_strategy.avg_views,
            min_engagement_rate=payload.search_strategy.min_engagement_rate,
            first_message=json.dumps(
                {
                    "subject": payload.email_first.subject,
                    "body": payload.email_first.email_body,
                }
            ),
            second_message=json.dumps(
                {
                    "subject": payload.email_later.subject,
                    "body": payload.email_later.email_body,
                }
            ),
            new_creators_expect_count=payload.target_new_creators,
            max_creators=payload.max_creators,
            plan_execute_time=_parse_datetime(payload.run_at_time),
            plan_stop_time=_parse_datetime(payload.run_end_time),
        )

        session.add(task)
        await session.commit()
        await session.refresh(task)

        return task

    # =========================
    # 任务四：更新任务
    # =========================
    @staticmethod
    async def update_task(
        session: AsyncSession,
        task_id: str,
        payload,
    ):
        """
        更新建联任务
        """
        stmt = select(OutreachTasks).where(OutreachTasks.id == task_id)
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()

        if not task:
            raise ResourceNotFoundError("outreach task")

        # 更新任务字段
        now = datetime.now(timezone.utc)
        task.task_name = payload.task_name
        task.last_modifier_id = "00000000-0000-0000-0000-000000000000"
        task.last_modification_time = now
        task.platform_campaign_id = payload.campaign_id
        task.platform_campaign_name = payload.campaign_name
        task.region = payload.region
        task.brand = payload.brand.name if hasattr(payload.brand, 'name') else str(payload.brand)
        task.message_send_strategy = int(payload.brand.only_first)
        if not task.task_type:
            task.task_type = "Connect"
        if payload.product_id is not None:
            task.platform_product_id = str(payload.product_id)
        if payload.product_name is not None:
            task.platform_product_name = payload.product_name
        if payload.product_list is not None:
            task.product_list = _normalize_product_list(payload.product_list)
        task.search_keywords = (
            payload.search_strategy.search_keywords or payload.brand.key_word
        )
        task.product_categories = payload.search_strategy.product_category
        task.fans_age_range = payload.search_strategy.fans_age_range
        task.fans_gender = payload.search_strategy.fans_gender
        task.content_types = payload.search_strategy.content_type
        task.gmv_range = (
            payload.search_strategy.gmv
            if payload.search_strategy.gmv not in (None, [])
            else payload.search_strategy.min_GMV
        )
        task.sales_range = (
            payload.search_strategy.sales
            if payload.search_strategy.sales not in (None, [])
            else payload.search_strategy.min_sales
        )
        task.min_fans = payload.search_strategy.min_fans
        task.min_avg_views = payload.search_strategy.avg_views
        task.min_engagement_rate = payload.search_strategy.min_engagement_rate
        task.first_message = json.dumps(
            {
                "subject": payload.email_first.subject,
                "body": payload.email_first.email_body,
            }
        )
        task.second_message = json.dumps(
            {
                "subject": payload.email_later.subject,
                "body": payload.email_later.email_body,
            }
        )
        task.new_creators_expect_count = payload.target_new_creators
        task.max_creators = payload.max_creators
        task.plan_execute_time = _parse_datetime(payload.run_at_time)
        task.plan_stop_time = _parse_datetime(payload.run_end_time)

        await session.commit()
        await session.refresh(task)

        return task

    # =========================
    # 任务五：立即执行任务
    # =========================
    @staticmethod
    async def run_task_now(
        session: AsyncSession,
        task_id: str,
    ):
        """
        立即执行任务（将计划执行时间设为当前时间）
        """
        stmt = select(OutreachTasks).where(OutreachTasks.id == task_id)
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()

        if not task:
            raise ResourceNotFoundError("outreach task")

        # 验证任务状态
        if task.status not in {"not_started", "pending"}:
            raise ValueError(f"任务状态为 {task.status}，无法立即执行")

        # 为了方便前端联调，直接将状态改为 running
        now = datetime.now(timezone.utc)
        task.plan_execute_time = now  # 更新计划执行时间
        task.real_start_at = now  # 设置实际开始时间
        task.status = "running"  # 直接改为执行中状态
        task.message = "任务已立即执行（前端联调模式）"
        task.last_modifier_id = "00000000-0000-0000-0000-000000000000"
        task.last_modification_time = now

        await session.commit()
        await session.refresh(task)

        return task

    # =========================
    # 任务六：更新任务名称
    # =========================
    @staticmethod
    async def update_task_name(
        session: AsyncSession,
        task_id: str,
        task_name: str,
    ) -> OutreachTasks:
        stmt = select(OutreachTasks).where(OutreachTasks.id == task_id)
        result = await session.execute(stmt)
        task = result.scalar_one_or_none()

        if not task:
            raise ResourceNotFoundError("outreach task")

        now = datetime.now(timezone.utc)
        task.task_name = task_name
        task.last_modifier_id = "00000000-0000-0000-0000-000000000000"
        task.last_modification_time = now

        await session.commit()
        await session.refresh(task)
        return task

    # =========================
    # 任务七：停止任务（批量）
    # =========================
    @staticmethod
    async def stop_tasks(
        session: AsyncSession,
        task_id: str | None = None,
    ) -> list[OutreachTasks]:
        stmt = select(OutreachTasks)
        if task_id:
            stmt = stmt.where(OutreachTasks.id == task_id)
        else:
            stmt = stmt.where(OutreachTasks.status.in_(["not_started", "running"]))

        result = await session.execute(stmt)
        tasks = result.scalars().all()
        if not tasks:
            return []

        now = datetime.now(timezone.utc)
        for task in tasks:
            task.status = "cancelled"
            task.message = "任务已停止"
            task.plan_stop_time = now
            if task.real_start_at and not task.real_end_at:
                task.real_end_at = now
            task.last_modifier_id = "00000000-0000-0000-0000-000000000000"
            task.last_modification_time = now

        await session.commit()
        return tasks

    # =========================
    # 任务八：构建爬虫 payload
    # =========================
    @staticmethod
    def build_crawler_payload(
        task: OutreachTasks,
        *,
        run_at_time_override: str | None = None,
    ) -> dict:
        first_message = OutreachTaskService._parse_message_json(task.first_message)
        second_message = OutreachTaskService._parse_message_json(task.second_message)

        first_body = first_message.get("body") or first_message.get("email_body")
        second_body = second_message.get("body") or second_message.get("email_body")

        email_first = None
        if first_message:
            email_first = {
                "subject": first_message.get("subject"),
                "email_body": first_body,
            }
        email_later = None
        if second_message:
            email_later = {
                "subject": second_message.get("subject"),
                "email_body": second_body,
            }

        search_strategy = {
            "search_keywords": task.search_keywords,
            "product_category": _list_or_empty(task.product_categories),
            "fans_age_range": _list_or_empty(task.fans_age_range),
            "fans_gender": task.fans_gender,
            "content_type": _list_or_empty(task.content_types),
            "gmv": _list_or_empty(task.gmv_range),
            "sales": _list_or_empty(task.sales_range),
            "min_GMV": task.gmv_range if not isinstance(task.gmv_range, list) else None,
            "min_sales": task.sales_range if not isinstance(task.sales_range, list) else None,
            "min_fans": task.min_fans,
            "avg_views": task.min_avg_views,
            "min_engagement_rate": task.min_engagement_rate,
        }

        run_at_time = run_at_time_override or _format_datetime(task.plan_execute_time)
        run_end_time = _format_datetime(task.plan_stop_time)
        product_list_value = (
            task.product_list
            if task.product_list not in (None, [], "")
            else task.platform_product_name
        )
        product_list = _list_or_empty(product_list_value)

        brand_payload = {
            "name": task.brand,
            "only_first": task.message_send_strategy or 0,
            "key_word": task.search_keywords,
        }

        task_metadata = {
            "task_name": task.task_name,
            "campaign_id": task.platform_campaign_id,
            "campaign_name": task.platform_campaign_name,
            "product_id": task.platform_product_id,
            "product_name": task.platform_product_name,
            "product_list": product_list,
            "region": task.region,
            "brand": brand_payload,
            "brand_name": task.brand,
            "only_first": task.message_send_strategy or 0,
            "task_type": task.task_type or "Connect",
            "message": task.message,
            "search_strategy": search_strategy,
            "email_first": email_first,
            "email_later": email_later,
            "email_first_body": first_body,
            "email_later_body": second_body,
            "target_new_creators": task.new_creators_expect_count,
            "max_creators": task.max_creators,
            "run_at_time": run_at_time,
            "run_end_time": run_end_time,
            "created_at": _format_datetime(task.creation_time),
        }

        payload = {
            "task_id": task.id,
            "platform": task.platform or "tiktok",
            "region": task.region,
            "brand_name": task.brand,
            "search_strategy": search_strategy,
            "max_creators_to_load": task.max_creators,
            "task_metadata": task_metadata,
        }
        return payload
