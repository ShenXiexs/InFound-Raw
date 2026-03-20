import { SampleManagementRow, SampleManagementTabKey } from './types'

export const SAMPLE_GROUP_LIST_URL = '/api/v1/affiliate/sample/group/list'
export const SAMPLE_PERFORMANCE_URL = '/api/v1/affiliate/sample/performance'
export const SAMPLE_TABLE_SELECTOR = '.arco-table'
export const SAMPLE_NEXT_SELECTOR = '.arco-table .arco-pagination li.arco-pagination-item-next'
export const SAMPLE_DRAWER_SELECTOR = '.arco-drawer'
export const SAMPLE_DRAWER_CLOSE_SELECTOR = '.arco-drawer-close-icon'

export interface SampleManagementTabConfig {
  displayName: string
  status: string
  sheetName: string
}

export const SAMPLE_MANAGEMENT_TAB_KEYS: SampleManagementTabKey[] = [
  'to_review',
  'ready_to_ship',
  'shipped',
  'in_progress',
  'completed'
]

export const TAB_CONFIG: Record<SampleManagementTabKey, SampleManagementTabConfig> = {
  to_review: {
    displayName: 'To review',
    status: 'ready to review',
    sheetName: 'to_review'
  },
  ready_to_ship: {
    displayName: 'Ready to ship',
    status: 'ready to ship',
    sheetName: 'ready_to_ship'
  },
  shipped: {
    displayName: 'Shipped',
    status: 'shipped',
    sheetName: 'shipped'
  },
  in_progress: {
    displayName: 'In progress',
    status: 'content pending',
    sheetName: 'in_progress'
  },
  completed: {
    displayName: 'Completed',
    status: 'completed',
    sheetName: 'completed'
  }
}

const COMMON_SHEET_COLUMNS: Array<keyof SampleManagementRow> = [
  'crawl_time',
  'tab',
  'status',
  'page_index',
  'group_index',
  'request_index',
  'group_id',
  'creator_id',
  'creator_name',
  'sample_request_id',
  'product_name',
  'product_id',
  'sku_id',
  'sku_desc',
  'sku_image',
  'commission_rate',
  'commission_rate_text',
  'region',
  'sku_stock',
  'expired_in_ms',
  'expired_in_text',
  'content_summary'
]

export const SAMPLE_MANAGEMENT_SHEET_COLUMNS: Record<SampleManagementTabKey, Array<keyof SampleManagementRow>> = {
  to_review: [...COMMON_SHEET_COLUMNS],
  ready_to_ship: [...COMMON_SHEET_COLUMNS],
  shipped: [...COMMON_SHEET_COLUMNS],
  in_progress: [...COMMON_SHEET_COLUMNS],
  completed: [...COMMON_SHEET_COLUMNS]
}
