"""Product 相关 schemas"""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

class ProductRecord(BaseModel):
    backend_system_id: Optional[str] = Field("", description="后端系统标识")
    region: str = Field(..., description="国家/地区")
    campaign_id: Optional[str] = Field("", description="活动 ID")
    campaign_name: Optional[str] = Field("", description="活动名称")
    product_name: str = Field(..., description="商品名称")
    thumbnail: Optional[str] = Field("", description="缩略图 URL")
    product_id: str = Field(..., description="商品 ID")
    sale_price: Optional[str] = Field("", description="售价区间")
    SKU_product: Optional[str] = Field("", description="SKU 名称（兼容旧字段）")
    shop_name: str = Field(..., description="店铺名称")
    campaign_start_time: Optional[str] = Field("", description="活动开始时间")
    campaign_end_time: Optional[str] = Field("", description="活动结束时间")
    creator_rate: Optional[str] = Field("", description="达人佣金比例")
    partner_rate: Optional[str] = Field("", description="机构佣金比例")
    cost_product: Optional[str] = Field("", description="商品成本")
    available_samples: Optional[str] = Field("", description="样品数量")
    stock: Optional[str] = Field("", description="库存")
    item_sold: Optional[str] = Field("", description="销量")
    affiliate_link: Optional[str] = Field("", description="联盟链接")
    product_link: str = Field(..., description="商品链接")
    product_name_cn: Optional[str] = Field("", description="商品中文名称")
    selling_point: Optional[str] = Field("", description="卖点（英文）")
    selling_point_cn: Optional[str] = Field("", description="卖点（中文）")
    shooting_guide: Optional[str] = Field("", description="拍摄指南（英文）")
    shooting_guide_cn: Optional[str] = Field("", description="拍摄指南（中文）")
    product_category_name: Optional[str] = Field("", description="商品品类名称")


class ProductUpdate(BaseModel):
    backend_system_id: Optional[str] = None
    region: Optional[str] = None
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    product_name: Optional[str] = None
    thumbnail: Optional[str] = None
    product_id: Optional[str] = None
    sale_price: Optional[str] = None
    SKU_product: Optional[str] = None
    shop_name: Optional[str] = None
    campaign_start_time: Optional[str] = None
    campaign_end_time: Optional[str] = None
    creator_rate: Optional[str] = None
    partner_rate: Optional[str] = None
    cost_product: Optional[str] = None
    available_samples: Optional[str] = None
    stock: Optional[str] = None
    item_sold: Optional[str] = None
    affiliate_link: Optional[str] = None
    product_link: Optional[str] = None
    product_name_cn: Optional[str] = None
    selling_point: Optional[str] = None
    selling_point_cn: Optional[str] = None
    shooting_guide: Optional[str] = None
    shooting_guide_cn: Optional[str] = None
    product_category_name: Optional[str] = None

class ProductBatchRequest(BaseModel):
    items: List[ProductRecord] = Field(..., description="商品记录列表")
    note: Optional[str] = Field(None, description="上传备注")
