"""
商品卡任务 API
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from api.deps import get_current_active_user
from schemas.card import CardTaskListResponse, CardTaskStatus
from services.card_service import get_card_service
from utils.response import create_response

router = APIRouter()


@router.post("/tasks", summary="上传 Excel 并生成/发送商品卡")
async def create_card_task(
    creator_file: UploadFile = File(..., description="达人信息 Excel"),
    product_file: UploadFile = File(..., description="商品信息 Excel"),
    headless: bool = Form(True, description="是否使用无头模式执行 Playwright"),
    verify_delivery: bool = Form(True, description="是否发送后检查聊天记录"),
    manual_login_timeout: int = Form(600, description="手动登录等待欢迎页的超时时间（秒）"),
    generate_only: bool = Form(False, description="仅生成 JSON，不执行发送"),
    region: str = Form("MX", description="账号所属地区代码，例如 MX 或 FR"),
    account_name: Optional[str] = Form(
        None, description="config/accounts.json 中的账号 name，留空则自动选择区域账号"
    ),
    current_user: dict = Depends(get_current_active_user),
):
    creator_bytes = await creator_file.read()
    product_bytes = await product_file.read()

    if not creator_bytes:
        raise HTTPException(status_code=400, detail="达人 Excel 文件为空")
    if not product_bytes:
        raise HTTPException(status_code=400, detail="商品 Excel 文件为空")

    service = get_card_service()
    task_id, status = service.submit_task(
        creator_bytes=creator_bytes,
        creator_filename=creator_file.filename or "",
        product_bytes=product_bytes,
        product_filename=product_file.filename or "",
        headless=headless,
        verify_delivery=verify_delivery,
        manual_login_timeout=manual_login_timeout,
        generate_only=generate_only,
        created_by=current_user["username"],
        region=region,
        account_name=account_name,
    )

    return create_response(
        success=True,
        message="任务已创建",
        data={
            "task_id": task_id,
            "status": status.model_dump(),
        },
    )


@router.get("/tasks", summary="查看商品卡任务列表", response_model=CardTaskListResponse)
async def list_card_tasks(
    current_user: dict = Depends(get_current_active_user),
):
    service = get_card_service()
    tasks = service.list_tasks()
    return CardTaskListResponse(tasks=tasks, total=len(tasks))


@router.get(
    "/tasks/{task_id}",
    summary="查看单个商品卡任务状态",
    response_model=CardTaskStatus,
)
async def get_card_task(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    service = get_card_service()
    status = service.get_task(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="任务不存在")
    return status


@router.post("/tasks/{task_id}/cancel", summary="取消尚未执行的商品卡任务")
async def cancel_card_task(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    service = get_card_service()
    cancelled = service.cancel_task(task_id)
    if not cancelled:
        raise HTTPException(status_code=409, detail="任务无法取消，可能已开始执行")
    return create_response(success=True, message="任务已取消")
