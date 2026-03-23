import type { SampleManagementTabKey } from '@sim-common/types/rpa-sample-management'
export type { SampleManagementTabKey } from '@sim-common/types/rpa-sample-management'

export interface SampleManagementRow {
  crawl_time: string
  tab: string
  status: string
  page_index: number
  group_index: number
  request_index: number
  group_id: string
  creator_id: string
  creator_name: string
  sample_request_id: string
  product_name: string
  product_id: string
  sku_id: string
  sku_desc: string
  sku_image: string
  commission_rate: number | null
  commission_rate_text: string
  region: string
  sku_stock: number | null
  expired_in_ms: number | null
  expired_in_text: string
  content_summary: string
}

export interface SampleManagementTabCrawlResult {
  tab: SampleManagementTabKey
  rows: SampleManagementRow[]
  pages_visited: number
  responses_captured: number
  stop_reason: string
  page_signatures: string[]
}

export interface SampleManagementExportResult {
  to_review: SampleManagementTabCrawlResult
  ready_to_ship: SampleManagementTabCrawlResult
  shipped: SampleManagementTabCrawlResult
  in_progress: SampleManagementTabCrawlResult
  completed: SampleManagementTabCrawlResult
  excel_path: string
}
