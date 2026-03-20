export interface SellerRpaReportConfigInput {
  enabled?: boolean
  baseUrl?: string
  authToken?: string
  authHeader?: string
  heartbeatIntervalSeconds?: number
}

export interface SellerRpaTaskContextInput {
  taskId?: string
  shopId?: string
  taskName?: string
  shopRegionCode?: string
  scheduledTime?: string
  crawlDate?: string
  report?: SellerRpaReportConfigInput
}
