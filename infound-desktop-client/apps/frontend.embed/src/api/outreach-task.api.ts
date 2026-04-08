import { request } from './http'

const OUTREACH_TASK_BASE_URL = '/outreach/settings'
const OUTREACH_TASK_LIST_BASE_URL = '/outreach/task-settings'
const OUTREACH_CREATOR_FILTER_ITEMS_URL = '/outreach/creator-filter-items'
const OUTREACH_TASK_DETAIL_BASE_URL = '/outreach/tasks'

export type OutreachTaskStatus = 'RUNNING' | 'NOT_STARTED' | 'ENDED' | 'COMPLETED'

export interface OutreachTaskItem {
  id: string
  taskName: string
  startTime: string
  planCount: number
  linkedCount: number
  duration: string
  spendTime: number
  status: string
}

export interface OutreachTaskListParams {
  page: number
  pageSize: number
}

export interface OutreachTaskListBody {
  shopId: string
  keyword?: string
  status?: string
}

export interface OutreachTaskListResult {
  total: number
  list: OutreachTaskItem[]
}

export interface CreatorFilterOption<T = string | number | boolean> {
  label: string
  value: T
}

export interface CreatorFilterTreeOption {
  label: string
  value: string
  raw_label?: string
  count_hint?: number
  children?: CreatorFilterTreeOption[]
}

export interface OutreachCreatorFilterItemsResult {
  creators?: {
    filters?: {
      productCategories?: {
        optionTree?: CreatorFilterTreeOption[]
      }
      avgCommissionRate?: {
        options?: CreatorFilterOption<string>[]
      }
      contentTypes?: {
        options?: CreatorFilterOption<string>[]
      }
      creatorAgency?: {
        options?: CreatorFilterOption<string>[]
      }
      fastGrowing?: {
        options?: CreatorFilterOption<boolean>[]
      }
      notInvitedInPast90Days?: {
        options?: CreatorFilterOption<boolean>[]
      }
    }
  }
  followers?: {
    filters?: {
      fansAgeRange?: {
        options?: CreatorFilterOption<string>[]
      }
      fansGender?: {
        options?: CreatorFilterOption<string>[]
      }
      fansCountRange?: {
        presetOptions?: CreatorFilterOption<string>[]
        inputItems?: Array<{
          index: number
          value: string
          dom_path?: string
          input_type?: string
          placeholder?: string
        }>
      }
    }
  }
  performance?: {
    filters?: {
      gmvRange?: {
        options?: CreatorFilterOption<string>[]
      }
      salesCountRange?: {
        options?: CreatorFilterOption<string>[]
      }
      minAvgVideoViews?: {
        presetOptions?: CreatorFilterOption<string>[]
        toggleOptionItems?: CreatorFilterOption<boolean>[]
      }
      minAvgLiveViews?: {
        presetOptions?: CreatorFilterOption<string>[]
        toggleOptionItems?: CreatorFilterOption<boolean>[]
      }
      minEngagementRate?: {
        presetOptions?: CreatorFilterOption<string>[]
        toggleOptionItems?: CreatorFilterOption<boolean>[]
      }
      sortBy?: {
        options?: CreatorFilterOption<number>[]
      }
    }
  }
}

const toNumber = (value: unknown, fallback: number = 0): number => {
  const num = Number(value)
  return Number.isFinite(num) ? num : fallback
}

const normalizeTaskListResult = (raw: any): OutreachTaskListResult => {
  const payload = raw?.data ?? raw ?? {}
  const listRaw = Array.isArray(payload?.list) ? payload.list : Array.isArray(payload?.records) ? payload.records : []
  const list: OutreachTaskItem[] = listRaw.map((item: any, index: number) => ({
    id: String(item?.id ?? item?.taskId ?? index),
    taskName: String(item?.taskName ?? item?.name ?? ''),
    startTime: String(item?.startTime ?? item?.startAt ?? ''),
    planCount: toNumber(item?.planCount ?? item?.planNumber ?? item?.plannedCount),
    linkedCount: toNumber(item?.linkedCount ?? item?.realCount ?? item?.completedCount ?? item?.finishedCount ?? item?.newCount),
    duration: String(item?.duration ?? item?.runDuration ?? ''),
    spendTime: toNumber(item?.spendTime, 0),
    status: String(item?.status ?? '')
  }))

  const total = toNumber(payload?.total ?? payload?.totalCount ?? list.length, list.length)
  return { total, list }
}

export interface CreateOutreachTaskPayload {
  shopId: string
  taskName: string
  startTime: string
  creatorFilter: {
    keyword: string
    productCategories: string[]
    avgCommissionRate: number
    contentTypes: number
    creatorAgency: number
    fastGrowing: string
    notInvitedInPast90Days: string
    fansAgeRange: string[]
    fansGender: number
    fansCountRange: {
      min: string
      max: string
    }
    gmvRange: string[]
    salesCountRange: string[]
    minAvgVideoViews: number
    minAvgLiveViews: number
    minEngagementRate: number
    creatorEstimatedPublishRate: number
    coBranding: string[]
    sortBy: number
  }
  plannedCount: string
  outreachMode: string
  firstMessage: string
  replyMessage: string
  attachProducts: boolean
  productIds: string
}

export interface UpdateOutreachTaskPayload {
  taskName?: string
  planCount?: number
  startTime?: string
  status?: OutreachTaskStatus
  [key: string]: any
}

export type OutreachTaskDetailResult = Record<string, any>
export type EditOutreachTaskPayload = CreateOutreachTaskPayload & {
  lastModificationTime: string
}
export interface TaskActionPayload {
  lastModificationTime: string
  shopId: string
}

export const getOutreachTaskList = async (params: OutreachTaskListParams, body: OutreachTaskListBody): Promise<OutreachTaskListResult> => {
  const shopId = body.shopId?.trim() || ''
  if (!shopId) {
    throw new Error('shopId is required')
  }

  const result = await request<any>({
    url: OUTREACH_TASK_LIST_BASE_URL,
    method: 'POST',
    params: {
      page: params.page,
      pageSize: params.pageSize
    },
    data: {
      shopId,
      keyword: body.keyword ?? '',
      status: body.status ?? ''
    }
  })
  return normalizeTaskListResult(result)
}

export const getOutreachCreatorFilterItems = async (shopId: string): Promise<OutreachCreatorFilterItemsResult> => {
  const normalizedShopId = shopId.trim()
  if (!normalizedShopId) {
    throw new Error('shopId is required')
  }

  const result = await request<any>({
    url: OUTREACH_CREATOR_FILTER_ITEMS_URL,
    method: 'GET',
    params: {
      shopId: normalizedShopId
    }
  })

  return result?.data ?? result ?? {}
}

export const createOutreachTask = async (payload: CreateOutreachTaskPayload): Promise<OutreachTaskItem> => {
  return await request<OutreachTaskItem>({
    url: OUTREACH_TASK_BASE_URL,
    method: 'POST',
    data: payload
  })
}

export const editOutreachTask = async (taskId: string, payload: EditOutreachTaskPayload): Promise<OutreachTaskItem> => {
  const normalizedTaskId = taskId.trim()
  if (!normalizedTaskId) {
    throw new Error('taskId is required')
  }

  return await request<OutreachTaskItem>({
    url: `${OUTREACH_TASK_DETAIL_BASE_URL}/${encodeURIComponent(normalizedTaskId)}`,
    method: 'PUT',
    data: payload
  })
}

export const getOutreachTaskDetail = async (taskId: string): Promise<OutreachTaskDetailResult> => {
  const normalizedTaskId = taskId.trim()
  if (!normalizedTaskId) {
    throw new Error('taskId is required')
  }

  return await request<OutreachTaskDetailResult>({
    url: `${OUTREACH_TASK_DETAIL_BASE_URL}/${encodeURIComponent(normalizedTaskId)}`,
    method: 'GET'
  })
}

export const updateOutreachTask = async (taskId: string, payload: UpdateOutreachTaskPayload): Promise<OutreachTaskItem> => {
  return await request<OutreachTaskItem>({
    url: `${OUTREACH_TASK_BASE_URL}/${taskId}`,
    method: 'PUT',
    data: payload
  })
}

export const startOutreachTask = async (taskId: string, payload: TaskActionPayload): Promise<void> => {
  await request<void>({
    url: `${OUTREACH_TASK_DETAIL_BASE_URL}/${encodeURIComponent(taskId.trim())}/start`,
    method: 'POST',
    data: payload
  })
}

export const stopOutreachTask = async (taskId: string, payload: TaskActionPayload): Promise<void> => {
  await request<void>({
    url: `${OUTREACH_TASK_DETAIL_BASE_URL}/${encodeURIComponent(taskId.trim())}/end`,
    method: 'POST'
    ,
    data: payload
  })
}

export const deleteOutreachTask = async (taskId: string): Promise<void> => {
  await request<void>({
    url: `${OUTREACH_TASK_BASE_URL}/${taskId}`,
    method: 'DELETE'
  })
}
