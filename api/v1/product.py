"""
产品卡片API
"""
from typing import Optional
from datetime import datetime
import shutil

from fastapi import APIRouter, Depends, Query, UploadFile, File, Form, HTTPException, status, Request, BackgroundTasks
from fastapi.concurrency import run_in_threadpool
from urllib.parse import unquote_plus
from api.deps import get_current_active_user
from utils.response import create_response
from database.products_repo import (
    list_products as list_products_repo,
    get_product as get_product_repo,
    update_product as update_product_repo,
    get_product_by_product_id as get_product_by_product_id_repo,
    update_product_by_product_id as update_product_by_product_id_repo,
    delete_product as delete_product_repo,
    delete_product_by_product_id as delete_product_by_product_id_repo,
    get_upload_batch_progress,
    get_upload_progress_summary,
)
from database.ingest_product_excel import (
    ingest_default_product_excel,
    get_default_product_excel_path,
    ingest_product_excel,
    ingest_product_records,
    get_product_data_dir,
    enrich_product_batch_async,
)
from schemas.product import ProductBatchRequest, ProductUpdate

router = APIRouter()

@router.post("/send", summary="发送产品卡片")
async def send_product_card(
    current_user: dict = Depends(get_current_active_user)
):
    """发送产品卡片 - TODO: 实现"""
    return create_response(success=True, data={"message": "Product功能待实现"})


@router.get("/upload-progress/summary", summary="查询全部上传任务的汇总进度")
async def get_upload_progress_summary_api(
    current_user: dict = Depends(get_current_active_user),
):
    summary = get_upload_progress_summary()
    return create_response(success=True, data=summary)

@router.get("/upload-progress/{batch_id}", summary="查询商品上传进度")
async def get_upload_progress(
    batch_id: int,
    current_user: dict = Depends(get_current_active_user),
):
    progress = get_upload_batch_progress(batch_id)
    if not progress:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到批次")
    return create_response(success=True, data=progress)

@router.get("/list", summary="查询商品列表")
async def list_products(
    request: Request,
    region: Optional[str] = Query(default=None, description="按地区筛选"),
    campaign_name: Optional[str] = Query(default=None, description="按活动名称筛选"),
    campaign_id: Optional[str] = Query(default=None, description="按活动ID筛选"),
    shop_name: Optional[str] = Query(default=None, description="按店铺名称筛选"),
    product_category_name: Optional[str] = Query(default=None, description="按品类筛选"),
    keyword: Optional[str] = Query(default=None, description="SKU或店铺模糊搜索"),
    page_num: int = Query(
        default=1,
        ge=1,
        alias="pageNum",
        description="页码（>=1，与任务列表保持一致）",
    ),
    page_size: int = Query(
        default=20,
        ge=1,
        alias="pageSize",
        description="每页数量，仅支持 10/20/50，默认 20",
    ),
    current_user: dict = Depends(get_current_active_user),
):
    """
    返回前端需要的商品字段，数据来源 product 表。
    """
    def _raw_query_value(key: str) -> Optional[str]:
        raw_qs = request.scope.get("query_string", b"")
        if not raw_qs:
            return None
        qs = raw_qs.decode()
        prefix = f"{key}="
        idx = qs.find(prefix)
        if idx == -1:
            return None
        start = idx + len(prefix)
        end = qs.find("&", start)
        raw_value = qs[start:] if end == -1 else qs[start:end]
        if not raw_value:
            return None
        return unquote_plus(raw_value).strip()

    if not shop_name:
        raw_shop = _raw_query_value("shop_name")
        if raw_shop:
            shop_name = raw_shop
    if not product_category_name:
        raw_category = _raw_query_value("product_category_name")
        if raw_category:
            product_category_name = raw_category

    allowed_sizes = {10, 20, 50}
    if page_size not in allowed_sizes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pageSize 仅支持 10/20/50",
        )
    effective_limit = page_size
    effective_offset = (page_num - 1) * effective_limit

    result = list_products_repo(
        region=region,
        campaign_name=campaign_name,
        campaign_id=campaign_id,
        shop_name=shop_name,
        product_category_name=product_category_name,
        keyword=keyword,
        offset=effective_offset,
        limit=effective_limit,
    )
    return create_response(success=True, data=result)

@router.get("/items/{product_id}", summary="获取单个商品")
async def get_product_detail(
    product_id: int,
    current_user: dict = Depends(get_current_active_user),
):
    record = get_product_repo(product_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到商品")
    return create_response(success=True, data=record)

@router.put("/items/{product_id}", summary="更新商品信息")
async def update_product_detail(
    product_id: int,
    payload: ProductUpdate,
    current_user: dict = Depends(get_current_active_user),
):
    update_data = payload.dict(exclude_unset=True)
    record = update_product_repo(product_id, update_data)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到商品")
    return create_response(success=True, data=record, message="商品信息已更新")

@router.get("/items/by-product-id/{external_id}", summary="根据业务 product_id 查询商品")
async def get_product_by_external_id(
    external_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    record = get_product_by_product_id_repo(external_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到商品")
    return create_response(success=True, data=record)

@router.put("/items/by-product-id/{external_id}", summary="根据业务 product_id 更新商品信息")
async def update_product_by_external_id(
    external_id: str,
    payload: ProductUpdate,
    current_user: dict = Depends(get_current_active_user),
):
    update_data = payload.dict(exclude_unset=True)
    result = update_product_by_product_id_repo(external_id, update_data)
    if not result["updated"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到商品")
    return create_response(success=True, data=result, message="商品信息已更新")

@router.delete("/items/{product_id}", summary="删除商品（按数据库ID）")
async def delete_product(
    product_id: int,
    current_user: dict = Depends(get_current_active_user),
):
    if not delete_product_repo(product_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到商品")
    return create_response(success=True, data={"deleted": True}, message="商品已删除")

@router.delete("/items/by-product-id/{external_id}", summary="删除商品（按业务 product_id）")
async def delete_product_by_external_id(
    external_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    deleted = delete_product_by_product_id_repo(external_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到商品")
    return create_response(success=True, data={"deleted": deleted}, message="商品已删除")

@router.post("/sync-from-excel", summary="从默认Excel同步商品数据")
async def sync_products_from_excel(
    use_dify: bool = Query(default=True, description="是否调用 Dify 自动补全"),
    region_override: Optional[str] = Query(default=None, description="覆盖 Excel 中缺失的 region"),
    current_user: dict = Depends(get_current_active_user),
):
    """
    将 data/product_data/product_list.xlsx 导入数据库，供内部运营手动触发。
    """
    result = await run_in_threadpool(
        ingest_default_product_excel,
        uploaded_by=current_user.get("username", "system"),
        use_dify=use_dify,
        override_region=region_override,
    )
    return create_response(
        success=True,
        data={
            "excel_path": str(get_default_product_excel_path()),
            "inserted": result["inserted"],
            "skipped": result["skipped"],
            "batch_id": result["batch_id"],
            "use_dify": use_dify,
        },
        message="商品库同步完成"
    )

@router.post("/upload-excel", summary="上传Excel并导入商品库")
async def upload_product_excel(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    note: Optional[str] = Form(default=None),
    use_dify: bool = Form(default=True),
    region_override: Optional[str] = Form(default=None),
    current_user: dict = Depends(get_current_active_user),
):
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 .xlsx / .xls 文件",
        )

    product_dir = get_product_data_dir()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = filename.replace(" ", "_")
    dest_path = product_dir / f"{timestamp}_{safe_name}"

    try:
        file.file.seek(0)
        with dest_path.open("wb") as dest:
            shutil.copyfileobj(file.file, dest)
    finally:
        file.file.close()

    try:
        result = await run_in_threadpool(
            ingest_product_excel,
            dest_path,
            current_user.get("username", "system"),
            note=note or filename,
            use_dify=False,
            override_region=region_override,
        )
    except Exception:
        dest_path.unlink(missing_ok=True)
        raise

    if use_dify:
        background_tasks.add_task(
            enrich_product_batch_async,
            result["batch_id"],
            dest_path,
            override_region=region_override,
        )

    return create_response(
        success=True,
        data={
            "excel_path": str(dest_path),
            "inserted": result["inserted"],
            "skipped": result["skipped"],
            "batch_id": result["batch_id"],
            "use_dify": use_dify,
            "enrichment_scheduled": bool(use_dify),
            "total_rows": result.get("total_rows"),
            "dify_total": result.get("dify_total"),
        },
        message="商品上传成功，Dify 正在后台处理中" if use_dify else "商品上传成功",
    )

@router.post("/batch", summary="批量写入商品记录")
async def batch_upsert_products(
    payload: ProductBatchRequest,
    current_user: dict = Depends(get_current_active_user),
):
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="items 不能为空",
        )

    records = [item.dict() for item in payload.items]
    total_rows = len(records)
    dify_total = sum(1 for r in records if r.get("product_link") or r.get("product_id"))
    result = ingest_product_records(
        records,
        uploaded_by=current_user.get("username", "system"),
        note=payload.note or "api-batch",
        source_file="api_json",
        total_rows=total_rows,
        dify_total=dify_total,
    )

    return create_response(
        success=True,
        data={
            "inserted": result["inserted"],
            "skipped": result["skipped"],
            "batch_id": result["batch_id"],
        },
        message="商品库写入完成",
    )
