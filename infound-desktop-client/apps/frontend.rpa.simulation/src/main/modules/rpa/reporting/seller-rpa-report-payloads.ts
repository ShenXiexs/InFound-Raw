import type { SellerCreatorDetailContextInput, SellerCreatorDetailData, SellerCreatorDetailPayloadInput } from '@common/types/rpa-creator-detail'
import type { OutreachFilterConfigInput } from '@common/types/rpa-outreach'
import type { SampleManagementPayloadInput } from '@common/types/rpa-sample-management'
import type { SampleManagementExportResult } from '../sample-management/types'
import { CREATOR_MARKETPLACE_DATA_KEY } from '../outreach/support'

interface RuntimeWindow {
  region: string
  startedAt: Date
  finishedAt: Date
}

const toIsoString = (value: Date): string => value.toISOString()

const toDateOnly = (value: Date): string => value.toISOString().slice(0, 10)

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
      send: 1
    }))
    .filter((item) => Boolean(item.platform_creator_id))
}

const normalizeCreatorDetailContext = (
  input?: SellerCreatorDetailContextInput
): Record<string, unknown> | undefined => {
  if (!input) {
    return undefined
  }

  const context: Record<string, unknown> = {}
  const stringFields: Array<[keyof SellerCreatorDetailContextInput, string]> = [
    ['platform', 'platform'],
    ['platformCreatorId', 'platform_creator_id'],
    ['platformCreatorUsername', 'platform_creator_username'],
    ['platformCreatorDisplayName', 'platform_creator_display_name'],
    ['chatUrl', 'chat_url'],
    ['searchKeyword', 'search_keyword'],
    ['searchKeywords', 'search_keywords'],
    ['brandName', 'brand_name'],
    ['currency', 'currency'],
    ['email', 'email'],
    ['whatsapp', 'whatsapp']
  ]

  stringFields.forEach(([sourceKey, targetKey]) => {
    const value = toText(input[sourceKey])
    if (value) {
      context[targetKey] = value
    }
  })

  if (input.categories !== undefined) {
    context.categories = input.categories
  }
  if (input.connect !== undefined) {
    context.connect = input.connect
  }
  if (input.reply !== undefined) {
    context.reply = input.reply
  }
  if (input.send !== undefined) {
    context.send = input.send
  }

  return Object.keys(context).length > 0 ? context : undefined
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
  return {
    task_id: taskId,
    shop_id: shopId,
    shop_region_code: toText(input.shopRegionCode) || meta.region,
    task_name: toText(input.taskName) || 'Playwright Outreach',
    task_type: 'OUTREACH',
    status: 'completed',
    message_send_strategy: toInteger(input.messageSendStrategy),
    message: toText(input.message),
    search_keyword: toText(input.searchKeyword),
    first_message: toText(input.firstMessage),
    second_message: toText(input.secondMessage),
    expect_count: toInteger(input.expectCount),
    real_count: creators.length,
    started_at: toIsoString(meta.startedAt),
    finished_at: toIsoString(meta.finishedAt),
    creators
  }
}

export const buildSampleMonitorResultPayload = (
  input: SampleManagementPayloadInput,
  result: SampleManagementExportResult,
  meta: RuntimeWindow
): Record<string, unknown> | null => {
  const shopId = toText(input.shopId)
  if (!shopId) {
    return null
  }

  return {
    shop_id: shopId,
    task_id: toText(input.taskId),
    crawl_date: toText(input.crawlDate) || toDateOnly(meta.finishedAt),
    result
  }
}

export const buildCreatorDetailResultPayload = (
  input: SellerCreatorDetailPayloadInput,
  detail: SellerCreatorDetailData,
  meta: RuntimeWindow
): Record<string, unknown> | null => {
  const shopId = toText(input.shopId)
  if (!shopId) {
    return null
  }

  return {
    shop_id: shopId,
    task_id: toText(input.taskId),
    crawl_date: toText(input.crawlDate) || toText(detail.collected_at_utc)?.slice(0, 10) || toDateOnly(meta.finishedAt),
    context: normalizeCreatorDetailContext(input.context),
    result: detail
  }
}
