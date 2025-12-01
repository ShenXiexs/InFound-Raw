# database/products_repo.py
# 查询骨架（给前端列表页用，database/products_repo.py）
from typing import Optional, Dict, Any
from datetime import timedelta
from sqlalchemy import select, and_, func, or_
from database.db import get_session, now_beijing
from database.models import Product, UploadBatch
from database.ingest_product_excel import _calc_cost_from_sale_price

PRODUCT_MUTABLE_FIELDS = {
    "backend_system_id",
    "region",
    "campaign_id",
    "campaign_name",
    "product_name",
    "thumbnail",
    "product_id",
    "SKU_product",
    "sale_price",
    "shop_name",
    "campaign_start_time",
    "campaign_end_time",
    "creator_rate",
    "partner_rate",
    "cost_product",
    "available_samples",
    "stock",
    "item_sold",
    "affiliate_link",
    "product_link",
    "product_name_cn",
    "selling_point",
    "selling_point_cn",
    "shooting_guide",
    "shooting_guide_cn",
    "product_category_name",
}


CATEGORY_MAPPINGS = {
    "Home Supplies": "600001",
    "Kitchenware": "600024",
    "Textiles & Soft Furnishings": "600154",
    "Household Appliances": "600942",
    "Womenswear & Underwear": "601152",
    "Shoes": "601352",
    "Beauty & Personal Care": "601450",
    "Phones & Electronics": "601739",
    "Computers & Office Equipment": "601755",
    "Pet Supplies": "602118",
    "Sports & Outdoor": "603014",
    "Toys": "604206",
    "Furniture": "604453",
    "Tools & Hardware": "604579",
    "Home Improvement": "604968",
    "Automotive & Motorcycle": "605196",
    "Fashion Accessories": "605248",
    "Food & Beverages": "700437",
    "Health": "700645",
    "Books, Magazines & Audio": "801928",
    "Kids' Fashion": "802184",
    "Menswear & Underwear": "824328",
    "Luggage & Bags": "824584",
    "Collections": "951432",
    "Jewellery Accessories & Derivatives": "953224",
}

_CATEGORY_NAME_BY_CODE = {code: name for name, code in CATEGORY_MAPPINGS.items()}
_CATEGORY_NAME_LOOKUP = {name.lower(): name for name in CATEGORY_MAPPINGS}


def _serialize_product(record: Product) -> Dict[str, Any]:
    def _val(value):
        return value or ""

    return {
        "id": record.id,
        "backend_system_id": _val(record.backend_system_id),
        "region": _val(record.region),
        "campaign_id": _val(record.campaign_id),
        "campaign_name": _val(record.campaign_name),
        "product_name": _val(record.product_name),
        "thumbnail": _val(record.thumbnail),
        "product_id": _val(record.product_id),
        "SKU_product": _val(record.SKU_product),
        "sale_price": _val(record.sale_price),
        "shop_name": _val(record.shop_name),
        "campaign_start_time": _val(record.campaign_start_time),
        "campaign_end_time": _val(record.campaign_end_time),
        "creator_rate": _val(record.creator_rate),
        "partner_rate": _val(record.partner_rate),
        "cost_product": _val(record.cost_product),
        "available_samples": _val(record.available_samples),
        "stock": _val(record.stock),
        "item_sold": _val(record.item_sold),
        "affiliate_link": _val(record.affiliate_link),
        "product_link": _val(record.product_link),
        "product_name_cn": _val(record.product_name_cn),
        "selling_point": _val(record.selling_point),
        "selling_point_cn": _val(record.selling_point_cn),
        "shooting_guide": _val(record.shooting_guide),
        "shooting_guide_cn": _val(record.shooting_guide_cn),
        "product_category_name": _val(record.product_category_name),
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def list_products(
    region: Optional[str] = None,
    campaign_name: Optional[str] = None,
    campaign_id: Optional[str] = None,
    shop_name: Optional[str] = None,
    product_category_name: Optional[str] = None,
    keyword: Optional[str] = None,  # 在多字段模糊搜
    offset: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    with get_session() as db:
        conds = []
        if region:
            conds.append(Product.region == region)
        if campaign_name:
            conds.append(Product.campaign_name == campaign_name)
        if campaign_id:
            conds.append(Product.campaign_id == campaign_id)
        if shop_name:
            conds.append(Product.shop_name.ilike(f"%{shop_name.strip()}%"))
        if product_category_name:
            raw_value = product_category_name.strip()
            target_name = None
            if not raw_value:
                pass
            else:
                lower_value = raw_value.lower()
                if lower_value in _CATEGORY_NAME_LOOKUP:
                    target_name = _CATEGORY_NAME_LOOKUP[lower_value]
                elif raw_value in _CATEGORY_NAME_BY_CODE:
                    target_name = _CATEGORY_NAME_BY_CODE[raw_value]
            if target_name:
                conds.append(Product.product_category_name.ilike(f"%{target_name}%"))
            else:
                conds.append(Product.product_category_name.ilike(f"%{raw_value}%"))
        if keyword:
            like = f"%{keyword}%"
            conds.append(
                or_(
                    Product.SKU_product.ilike(like),
                    Product.shop_name.ilike(like),
                    Product.product_name.ilike(like),
                    Product.product_id.ilike(like),
                )
            )

        stmt = select(Product)
        count_stmt = select(func.count()).select_from(Product)
        if conds:
            condition = and_(*conds)
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(Product.created_at.desc()).offset(offset).limit(limit)

        rows = db.execute(stmt).scalars().all()
        total = db.execute(count_stmt).scalar() or 0
        items = [_serialize_product(r) for r in rows]
        return {"items": items, "total": total}


def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    with get_session() as db:
        record = db.get(Product, product_id)
        if not record:
            return None
        return _serialize_product(record)


def update_product(product_id: int, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = {k: v for k, v in payload.items() if k in PRODUCT_MUTABLE_FIELDS}
    if not data:
        return get_product(product_id)

    with get_session() as db:
        record = db.get(Product, product_id)
        if not record:
            return None

        if "sale_price" in data and "cost_product" not in data:
            computed_cost = _calc_cost_from_sale_price(data.get("sale_price", ""))
            if computed_cost:
                data["cost_product"] = computed_cost

        for key, value in data.items():
            setattr(record, key, value if value is not None else "")

        record.updated_at = now_beijing()
        db.flush()
        db.refresh(record)
        return _serialize_product(record)


def get_upload_batch_progress(batch_id: int) -> Optional[Dict[str, Any]]:
    with get_session() as db:
        batch = db.get(UploadBatch, batch_id)
        if not batch:
            return None
        return {
            "batch_id": batch.id,
            "uploaded_by": batch.uploaded_by,
            "note": batch.note or "",
            "source_file": batch.source_file or "",
            "uploaded_at": batch.uploaded_at.isoformat() if batch.uploaded_at else None,
            "total_rows": batch.total_rows or 0,
            "dify_total": batch.dify_total or 0,
            "dify_processed": batch.dify_processed or 0,
            "dify_failed": batch.dify_failed or 0,
            "region_override": batch.region_override or "",
        }


def get_upload_progress_summary() -> Dict[str, Any]:
    with get_session() as db:
        aggregate = db.execute(
            select(
                func.count(UploadBatch.id).label("batch_count"),
                func.coalesce(func.sum(UploadBatch.total_rows), 0).label("total_rows"),
                func.coalesce(func.sum(UploadBatch.dify_total), 0).label("dify_total"),
                func.coalesce(func.sum(UploadBatch.dify_processed), 0).label("dify_processed"),
                func.coalesce(func.sum(UploadBatch.dify_failed), 0).label("dify_failed"),
                func.max(UploadBatch.uploaded_at).label("last_uploaded_at"),
            )
        ).one()
        active = db.execute(
            select(
                func.count(UploadBatch.id).label("processing_batches"),
                func.coalesce(func.sum(UploadBatch.dify_total), 0).label("processing_total"),
                func.coalesce(func.sum(UploadBatch.dify_processed), 0).label("processing_processed"),
                func.coalesce(func.sum(UploadBatch.dify_failed), 0).label("processing_failed"),
                func.min(UploadBatch.uploaded_at).label("first_processing_at"),
            ).where(UploadBatch.dify_total > UploadBatch.dify_processed)
        ).one()
        dify_total = int(aggregate.dify_total or 0)
        dify_processed = int(aggregate.dify_processed or 0)
        dify_failed = int(aggregate.dify_failed or 0)
        dify_success = max(dify_processed - dify_failed, 0)
        dify_remaining = max(dify_total - dify_processed, 0)

        processing_total = int(active.processing_total or 0)
        processing_processed = int(active.processing_processed or 0)
        processing_failed = int(active.processing_failed or 0)
        processing_success = max(processing_processed - processing_failed, 0)
        processing_remaining = max(processing_total - processing_processed, 0)
        processing_batches = int(active.processing_batches or 0)

        first_processing_at = active.first_processing_at
        now = now_beijing()
        if first_processing_at and first_processing_at.tzinfo is None:
            first_processing_at = first_processing_at.replace(tzinfo=now.tzinfo)
        elapsed_seconds = (
            int((now - first_processing_at).total_seconds())
            if first_processing_at
            else 0
        )
        per_row_seconds = 75
        estimated_total_seconds = processing_total * per_row_seconds
        estimated_remaining_seconds = processing_remaining * per_row_seconds
        estimated_finish_dt = (
            now + timedelta(seconds=estimated_remaining_seconds)
            if processing_remaining > 0
            else None
        )
        estimated_finish_iso = (
            estimated_finish_dt.isoformat() if estimated_finish_dt else None
        )

        summary = {
            "batch_count": int(aggregate.batch_count or 0),
            "total_rows": int(aggregate.total_rows or 0),
            "dify_total": dify_total,
            "dify_processed": dify_processed,
            "dify_failed": dify_failed,
            "dify_success": dify_success,
            "dify_remaining": dify_remaining,
            "last_uploaded_at": (
                aggregate.last_uploaded_at.isoformat()
                if aggregate.last_uploaded_at
                else None
            ),
            "processing": {
                "batches": processing_batches,
                "rows_total": processing_total,
                "rows_success": processing_success,
                "rows_failed": processing_failed,
                "rows_remaining": processing_remaining,
                "started_at": (
                    first_processing_at.isoformat()
                    if first_processing_at
                    else None
                ),
                "elapsed_seconds": elapsed_seconds if processing_batches else 0,
                "estimated_total_seconds": estimated_total_seconds if processing_batches else 0,
                "estimated_remaining_seconds": estimated_remaining_seconds if processing_batches else 0,
                "estimated_finish_at": estimated_finish_iso if processing_batches else None,
            },
        }
        return summary


def get_product_by_product_id(external_id: str) -> Optional[Dict[str, Any]]:
    normalized = (external_id or "").strip()
    if not normalized:
        return None

    with get_session() as db:
        stmt = (
            select(Product)
            .where(Product.product_id == normalized)
            .order_by(Product.updated_at.desc())
            .limit(1)
        )
        record = db.execute(stmt).scalars().first()
        if not record:
            return None
        return _serialize_product(record)


def update_product_by_product_id(external_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = (external_id or "").strip()
    data = {k: v for k, v in (payload or {}).items() if k in PRODUCT_MUTABLE_FIELDS}
    if not normalized or not data:
        return {"updated": 0, "items": []}

    with get_session() as db:
        stmt = select(Product).where(Product.product_id == normalized)
        records = db.execute(stmt).scalars().all()
        if not records:
            return {"updated": 0, "items": []}

        if "sale_price" in data and "cost_product" not in data:
            computed_cost = _calc_cost_from_sale_price(data.get("sale_price", ""))
            if computed_cost:
                data["cost_product"] = computed_cost

        now = now_beijing()
        serialized = []
        for record in records:
            for key, value in data.items():
                setattr(record, key, value if value is not None else "")
            record.updated_at = now
            db.flush()
            db.refresh(record)
            serialized.append(_serialize_product(record))
        return {"updated": len(records), "items": serialized}


def delete_product(product_id: int) -> bool:
    with get_session() as db:
        record = db.get(Product, product_id)
        if not record:
            return False
        db.delete(record)
        return True


def delete_product_by_product_id(external_id: str) -> int:
    normalized = (external_id or "").strip()
    if not normalized:
        return 0

    with get_session() as db:
        stmt = select(Product).where(Product.product_id == normalized)
        records = db.execute(stmt).scalars().all()
        if not records:
            return 0
        deleted = 0
        for record in records:
            db.delete(record)
            deleted += 1
        return deleted


def reset_upload_batches() -> Dict[str, int]:
    """
    清空所有 upload_batch 记录以及对应的 product 记录。
    """
    with get_session() as db:
        deleted_products = db.query(Product).delete(synchronize_session=False)
        deleted_batches = db.query(UploadBatch).delete(synchronize_session=False)
        return {"products": deleted_products, "batches": deleted_batches}
