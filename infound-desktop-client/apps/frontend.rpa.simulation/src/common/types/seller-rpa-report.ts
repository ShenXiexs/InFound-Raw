export interface SellerRpaReportConfigInput {
  enabled?: boolean
  baseUrl?: string
  authToken?: string
  authHeader?: string
}

export interface SellerRpaTaskContextInput {
  taskId?: string
  shopId?: string
  taskName?: string
  shopRegionCode?: string
  scheduledTime?: string
  report?: SellerRpaReportConfigInput
}
