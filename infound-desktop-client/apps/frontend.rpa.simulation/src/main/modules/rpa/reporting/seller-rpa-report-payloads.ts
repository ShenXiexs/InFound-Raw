import type { OutreachFilterConfigInput } from '@sim-common/types/rpa-outreach'
import type {
  SellerCreatorDetailData,
  SellerCreatorDetailPayloadInput
} from '@sim-common/types/rpa-creator-detail'
import type { SampleManagementPayloadInput } from '@sim-common/types/rpa-sample-management'
import { CREATOR_MARKETPLACE_DATA_KEY, mergeOutreachFilterConfig } from '../outreach/support'
import type { SampleManagementExportResult } from '../sample-management/types'

interface RuntimeWindow {
  region: string
  startedAt: Date
  finishedAt: Date
}

const toIsoString = (value: Date): string => value.toISOString()

const toText = (value: unknown): string | undefined => {
  const text = String(value ?? '').trim()
  return text || undefined
}

const toInteger = (value: unknown): number | undefined => {
  if (value === null || value === undefined || value === '') {
    return undefined
  }
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) {
    return undefined
  }
  return Math.trunc(numeric)
}

const toPlainObject = (value: unknown): Record<string, unknown> | undefined => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return undefined
  }
  return value as Record<string, unknown>
}

const normalizeCreatorItems = (runtimeData: Record<string, unknown>): Array<Record<string, unknown>> => {
  const rawItems = runtimeData[CREATOR_MARKETPLACE_DATA_KEY]
  if (!Array.isArray(rawItems)) {
    return []
  }
  return rawItems
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object' && !Array.isArray(item))
    .map((item) => ({
      platform_creator_id: toText(item.creator_id ?? item.platform_creator_id),
      creator_name: toText(item.creator_name),
      avatar_url: toText(item.avatar_url),
      category: toText(item.category),
      send:
        typeof item.send === 'boolean'
          ? item.send
            ? 1
            : 0
          : toInteger(item.send),
      send_time: toText(item.send_time)
    }))
    .filter((item) => Boolean(item.platform_creator_id))
}

export const buildOutreachResultPayload = (
  input: OutreachFilterConfigInput,
  runtimeData: Record<string, unknown>,
  meta: RuntimeWindow
): Record<string, unknown> | null => {
  const taskId = toText(input.taskId)
  const shopId = toText(input.shopId)
  if (!taskId || !shopId) {
    return null
  }

  const creators = normalizeCreatorItems(runtimeData)
  const mergedConfig = mergeOutreachFilterConfig(input)
  return {
    task_id: taskId,
    shop_id: shopId,
    shop_region_code: toText(input.shopRegionCode) || meta.region,
    task_name: toText(input.taskName) || 'Playwright Outreach',
    task_type: 'OUTREACH',
    status: 'completed',
    duplicate_check_type: toInteger(input.duplicateCheckType),
    duplicate_check_code: toText(input.duplicateCheckCode),
    message_send_strategy: toInteger(input.messageSendStrategy),
    message: toText(input.message),
    search_keyword: toText(mergedConfig.searchKeyword),
    first_message: toText(input.firstMessage),
    second_message: toText(input.secondMessage),
    filter_sort_by: toInteger(input.filterSortBy),
    plan_execute_time: toInteger(input.planExecuteTime),
    expect_count: toInteger(input.expectCount),
    real_count: creators.length,
    started_at: toIsoString(meta.startedAt),
    finished_at: toIsoString(meta.finishedAt),
    creator_filters: mergedConfig.creatorFilters,
    follower_filters: mergedConfig.followerFilters,
    performance_filters: mergedConfig.performanceFilters,
    creators
  }
}

export const buildCreatorDetailResultPayload = (
  input: SellerCreatorDetailPayloadInput,
  detail: SellerCreatorDetailData,
  meta: RuntimeWindow
): Record<string, unknown> | null => {
  const taskId = toText(input.taskId)
  const shopId = toText(input.shopId)
  if (!taskId || !shopId) {
    return null
  }

  return {
    task_id: taskId,
    shop_id: shopId,
    shop_region_code: toText(input.shopRegionCode) || meta.region,
    task_name: toText(input.taskName) || 'Playwright Creator Detail',
    platform: 'tiktok',
    detail,
    context: toPlainObject(input.context)
  }
}

export const buildSampleMonitorResultPayload = (
  input: SampleManagementPayloadInput,
  result: SampleManagementExportResult,
  meta: RuntimeWindow
): Record<string, unknown> | null => {
  const taskId = toText(input.taskId)
  const shopId = toText(input.shopId)
  if (!taskId || !shopId) {
    return null
  }

  return {
    task_id: taskId,
    shop_id: shopId,
    shop_region_code: toText(input.shopRegionCode) || meta.region,
    task_name: toText(input.taskName) || 'Playwright Sample Monitor',
    started_at: toIsoString(meta.startedAt),
    finished_at: toIsoString(meta.finishedAt),
    tabs: Array.isArray(input.tabs) ? input.tabs : input.tab ? [input.tab] : [],
    result
  }
}
