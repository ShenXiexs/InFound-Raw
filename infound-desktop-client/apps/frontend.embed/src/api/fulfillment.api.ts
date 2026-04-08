import { request } from './http'

const FULFILLMENT_TASK_BASE_URL = '/api/embed/fulfillment/tasks'
const FULFILLMENT_RULE_BASE_URL = '/contract/rules'
const FULFILLMENT_REMINDER_LAST_24H_COUNT_URL = '/contract/reminder-records/last-24h-count'

export type FulfillmentTaskStatus = 'RUNNING' | 'PENDING' | 'COMPLETED' | 'ERROR'

export interface FulfillmentTaskItem {
  id: string
  taskName: string
  startTime: string
  plannedOrders: number
  fulfilledOrders: number
  abnormalOrders: number
  status: FulfillmentTaskStatus
}

export interface FulfillmentTaskListParams {
  keyword?: string
  status?: FulfillmentTaskStatus
  page?: number
  pageSize?: number
}

export interface FulfillmentTaskListResult {
  total: number
  list: FulfillmentTaskItem[]
}

export interface FulfillmentReminderRecordItem {
  [key: string]: any
}

export interface FulfillmentReminderRecordListResult {
  total: number
  list: FulfillmentReminderRecordItem[]
}

export interface FulfillmentRuleItem {
  ruleCode: string
  name: string
  description: string
  remark?: string | null
  message?: string | null
  isConfigured: boolean
  isActive: boolean
  canEnable: boolean
}

export interface CreateFulfillmentTaskPayload {
  taskName: string
  plannedOrders: number
  startTime?: string
}

export interface UpdateFulfillmentTaskPayload {
  taskName?: string
  plannedOrders?: number
  startTime?: string
  status?: FulfillmentTaskStatus
}

export interface SetFulfillmentRuleEnabledPayload {
  shopId: string
  message: string
  isActive: string
}

export interface UpdateFulfillmentRulePayload {
  shopId: string
  message: string
  isActive: string
}

export interface FulfillmentReminderRecordListPayload {
  shopId: string
  ruleCode?: string
}

export const getFulfillmentReminderLast24hCount = async (shopId: string): Promise<number> => {
  const normalizedShopId = shopId.trim()
  if (!normalizedShopId) {
    throw new Error('shopId is required')
  }

  const result = await request<any>({
    url: FULFILLMENT_REMINDER_LAST_24H_COUNT_URL,
    method: 'GET',
    params: {
      shopId: normalizedShopId
    }
  })

  const value = result?.data?.count
  const normalizedValue = Number(value ?? 0)
  return Number.isFinite(normalizedValue) ? normalizedValue : 0
}

export const getFulfillmentReminderRecordList = async (
  params: {
    page: number
    pageSize: number
  },
  payload: FulfillmentReminderRecordListPayload
): Promise<FulfillmentReminderRecordListResult> => {
  const normalizedShopId = payload.shopId.trim()
  if (!normalizedShopId) {
    throw new Error('shopId is required')
  }

  const result = await request<any>({
    url: '/contract/reminder-records',
    method: 'POST',
    params: {
      page: params.page,
      pageSize: params.pageSize
    },
    data: {
      shopId: normalizedShopId,
      ruleCode: payload.ruleCode ?? ''
    }
  })

  const responsePayload = result?.data ?? result ?? {}
  const dataPayload = responsePayload?.data ?? {}
  const list = Array.isArray(dataPayload?.items)
    ? dataPayload.items
    : dataPayload?.items && typeof dataPayload.items === 'object'
      ? [dataPayload.items]
      : Array.isArray(dataPayload?.list)
        ? dataPayload.list
        : Array.isArray(dataPayload?.records)
          ? dataPayload.records
          : Array.isArray(dataPayload)
            ? dataPayload
            : []
  const totalValue = dataPayload?.total ?? dataPayload?.count ?? list.length
  const total = Number(totalValue)

  return {
    total: Number.isFinite(total) ? total : list.length,
    list
  }
}

export const getFulfillmentRuleList = async (shopId: string): Promise<FulfillmentRuleItem[]> => {
  const normalizedShopId = shopId.trim()
  if (!normalizedShopId) {
    throw new Error('shopId is required')
  }

  const result = await request<any>({
    url: FULFILLMENT_RULE_BASE_URL,
    method: 'GET',
    params: {
      shopId: normalizedShopId
    }
  })

  const payload = result?.data ?? result ?? []
  if (Array.isArray(payload)) {
    return payload as FulfillmentRuleItem[]
  }

  if (Array.isArray(payload?.list)) {
    return payload.list as FulfillmentRuleItem[]
  }

  if (Array.isArray(payload?.records)) {
    return payload.records as FulfillmentRuleItem[]
  }

  if (payload && typeof payload === 'object' && 'ruleCode' in payload) {
    return [payload as FulfillmentRuleItem]
  }

  return []
}

export const setFulfillmentRuleEnabled = async (
  ruleCode: string,
  payload: SetFulfillmentRuleEnabledPayload
): Promise<void> => {
  const normalizedRuleCode = ruleCode.trim()
  if (!normalizedRuleCode) {
    throw new Error('ruleCode is required')
  }

  await request<void>({
    url: `${FULFILLMENT_RULE_BASE_URL}/${encodeURIComponent(normalizedRuleCode)}`,
    method: 'PUT',
    data: payload
  })
}

export const updateFulfillmentRule = async (
  ruleCode: string,
  payload: UpdateFulfillmentRulePayload
): Promise<void> => {
  const normalizedRuleCode = ruleCode.trim()
  if (!normalizedRuleCode) {
    throw new Error('ruleCode is required')
  }

  await request<void>({
    url: `${FULFILLMENT_RULE_BASE_URL}/${encodeURIComponent(normalizedRuleCode)}`,
    method: 'PUT',
    data: payload
  })
}

export const getFulfillmentTaskList = async (params: FulfillmentTaskListParams): Promise<FulfillmentTaskListResult> => {
  return await request<FulfillmentTaskListResult>({
    url: FULFILLMENT_TASK_BASE_URL,
    method: 'GET',
    params
  })
}

export const createFulfillmentTask = async (payload: CreateFulfillmentTaskPayload): Promise<FulfillmentTaskItem> => {
  return await request<FulfillmentTaskItem>({
    url: FULFILLMENT_TASK_BASE_URL,
    method: 'POST',
    data: payload
  })
}

export const updateFulfillmentTask = async (taskId: string, payload: UpdateFulfillmentTaskPayload): Promise<FulfillmentTaskItem> => {
  return await request<FulfillmentTaskItem>({
    url: `${FULFILLMENT_TASK_BASE_URL}/${taskId}`,
    method: 'PUT',
    data: payload
  })
}

export const retryFulfillmentTask = async (taskId: string): Promise<void> => {
  await request<void>({
    url: `${FULFILLMENT_TASK_BASE_URL}/${taskId}/retry`,
    method: 'POST'
  })
}

export const deleteFulfillmentTask = async (taskId: string): Promise<void> => {
  await request<void>({
    url: `${FULFILLMENT_TASK_BASE_URL}/${taskId}`,
    method: 'DELETE'
  })
}
