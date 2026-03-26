from typing import Any

from fastapi import APIRouter, Query, Depends

from apps.portal_operation_open_api.core.deps import get_outreach_task_service
from apps.portal_operation_open_api.core.rabbitmq_producer import RabbitMQProducer
from apps.portal_operation_open_api.services.outreach_task_service import (
    OutreachTaskService,
)
from core_base import get_logger, APIResponse, success_response

router = APIRouter(tags=["首页"])
logger = get_logger()
UUID_PATTERN = r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"


@router.get(
    "/",
    response_model=APIResponse[Any],
    response_model_by_alias=True,
)
async def index(
        task_id: str | None = Query(
            None,
            description="任务ID（可选）",
            pattern=UUID_PATTERN,
        ),
        service: OutreachTaskService = Depends(get_outreach_task_service),
) -> APIResponse[Any]:
    tasks = await service.stop_tasks(task_id)

    if tasks:
        for task in tasks:
            try:
                queue_name, routing_key_prefix = RabbitMQProducer.build_outreach_task_binding(task.id)
                await RabbitMQProducer.publish_outreach_control_message(
                    action="end",
                    task_id=task.id,
                    queue_name=queue_name,
                    routing_key_prefix=routing_key_prefix,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to publish outreach stop control",
                    task_id=task.id,
                    error=str(exc),
                )

    return success_response({
        "stopped": len(tasks),
        "task_ids": [task.id for task in tasks],
    })
