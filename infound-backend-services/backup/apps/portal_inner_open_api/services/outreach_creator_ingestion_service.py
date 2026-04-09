from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from common.models.infound import Creators, CreatorCrawlLogs
from common.core.logger import get_logger
from apps.portal_inner_open_api.models.outreach_creator import (
    OutreachCreatorIngestionRequest,
    OutreachCreatorIngestionResult,
)

logger = get_logger()


class OutreachCreatorIngestionService:
    """建联创作者数据入库服务"""

    @staticmethod
    async def ingest(
        payload: OutreachCreatorIngestionRequest,
        session: AsyncSession,
    ) -> OutreachCreatorIngestionResult:
        """
        处理建联创作者数据上报

        逻辑：
        1. 遍历每个创作者
        2. 检查 creators 表是否已存在（根据 platform + platform_creator_id）
        3. 如果不存在，插入 creators 表
        4. 插入 creator_crawl_logs 表（记录本次抓取）
        """
        now = datetime.now(timezone.utc)
        success_count = 0
        failed_count = 0

        for creator_row in payload.creators:
            try:
                # 检查创作者是否已存在
                stmt = select(Creators).where(
                    Creators.platform == payload.platform,
                    Creators.platform_creator_id == creator_row.platform_creator_id,
                )
                result = await session.execute(stmt)
                existing_creator = result.scalar_one_or_none()

                creator_id = existing_creator.id if existing_creator else str(uuid4())

                if not existing_creator:
                    # 创建新创作者
                    new_creator = Creators(
                        id=creator_id,
                        platform=payload.platform,
                        platform_creator_id=creator_row.platform_creator_id,
                        platform_creator_display_name=creator_row.platform_creator_display_name,
                        platform_creator_username=creator_row.platform_creator_username,
                        creator_id=payload.operator_id,
                        creation_time=now,
                        last_modifier_id=payload.operator_id,
                        last_modification_time=now,
                        email=creator_row.email,
                        whatsapp=creator_row.whatsapp,
                        introduction=creator_row.introduction,
                        region=creator_row.region,
                    )
                    session.add(new_creator)
                else:
                    # 更新现有创作者信息
                    existing_creator.platform_creator_display_name = creator_row.platform_creator_display_name
                    existing_creator.platform_creator_username = creator_row.platform_creator_username
                    existing_creator.last_modifier_id = payload.operator_id
                    existing_creator.last_modification_time = now
                    if creator_row.email:
                        existing_creator.email = creator_row.email
                    if creator_row.whatsapp:
                        existing_creator.whatsapp = creator_row.whatsapp
                    if creator_row.introduction:
                        existing_creator.introduction = creator_row.introduction
                    if creator_row.region:
                        existing_creator.region = creator_row.region

                # 插入抓取日志
                crawl_log = CreatorCrawlLogs(
                    id=str(uuid4()),
                    crawl_date=now.date(),
                    platform=payload.platform,
                    platform_creator_id=creator_row.platform_creator_id,
                    platform_creator_display_name=creator_row.platform_creator_display_name,
                    platform_creator_username=creator_row.platform_creator_username,
                    creator_id=payload.operator_id,
                    creation_time=now,
                    last_modifier_id=payload.operator_id,
                    last_modification_time=now,
                    email=creator_row.email,
                    whatsapp=creator_row.whatsapp,
                    introduction=creator_row.introduction,
                )
                session.add(crawl_log)

                success_count += 1

            except Exception as e:
                logger.error(
                    "创作者数据入库失败",
                    task_id=payload.task_id,
                    creator_id=creator_row.platform_creator_id,
                    error=str(e),
                    exc_info=True,
                )
                failed_count += 1

        # 提交事务
        await session.commit()

        logger.info(
            "建联创作者数据入库完成",
            task_id=payload.task_id,
            total=len(payload.creators),
            success=success_count,
            failed=failed_count,
        )

        return OutreachCreatorIngestionResult(
            task_id=payload.task_id,
            total_count=len(payload.creators),
            success_count=success_count,
            failed_count=failed_count,
        )


outreach_creator_ingestion_service = OutreachCreatorIngestionService()
