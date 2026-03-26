from __future__ import annotations

from typing import Any, Optional

from pydantic import Field

from shared_application_services import BaseDTO


class SampleMonitorRowItem(BaseDTO):
    crawl_time: Optional[Any] = None
    tab: Optional[str] = None
    status: Optional[str] = None
    page_index: Optional[int] = None
    group_index: Optional[int] = None
    request_index: Optional[int] = None
    group_id: Optional[str] = None
    creator_id: Optional[str] = None
    creator_name: Optional[str] = None
    sample_request_id: Optional[str] = None
    product_name: Optional[str] = None
    product_id: Optional[str] = None
    sku_id: Optional[str] = None
    sku_desc: Optional[str] = None
    sku_image: Optional[str] = None
    commission_rate: Optional[Any] = None
    commission_rate_text: Optional[str] = None
    region: Optional[str] = None
    sku_stock: Optional[Any] = None
    expired_in_ms: Optional[Any] = None
    expired_in_text: Optional[str] = None
    content_summary: Optional[Any] = None


class SampleMonitorTabResult(BaseDTO):
    tab: Optional[str] = None
    rows: list[SampleMonitorRowItem] = Field(default_factory=list)
    pages_visited: Optional[int] = None
    responses_captured: Optional[int] = None
    stop_reason: Optional[str] = None
    page_signatures: list[str] = Field(default_factory=list)


class SampleMonitorExportResult(BaseDTO):
    to_review: Optional[SampleMonitorTabResult] = None
    ready_to_ship: Optional[SampleMonitorTabResult] = None
    shipped: Optional[SampleMonitorTabResult] = None
    in_progress: Optional[SampleMonitorTabResult] = None
    completed: Optional[SampleMonitorTabResult] = None
    excel_path: Optional[str] = None


class SampleMonitorResultIngestionRequest(BaseDTO):
    task_id: str = Field(..., min_length=1)
    shop_id: str = Field(..., min_length=1)
    shop_region_code: Optional[str] = None
    task_name: Optional[str] = None
    started_at: Optional[Any] = None
    finished_at: Optional[Any] = None
    tabs: list[str] = Field(default_factory=list)
    result: SampleMonitorExportResult


class SampleMonitorResultIngestionResult(BaseDTO):
    task_id: str
    rows_processed: int
    product_upserts: int
    sample_upserts: int
    sample_content_upserts: int
    sample_crawl_logs_inserted: int
    sample_content_crawl_logs_inserted: int
