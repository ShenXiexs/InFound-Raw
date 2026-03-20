import type { CapturedJsonResponse } from './capture'
import { TAB_CONFIG } from './config'
import type { SampleManagementRow, SampleManagementTabKey } from './types'

export interface ParsedSampleManagementPage {
  rows: SampleManagementRow[]
  hasMore?: boolean
  pageSignature: string
}

export interface SampleManagementContentItem {
  content_type: string
  content_id: string
  cover_img: string
  content_title: string
  content_like: number | null
  content_order: number | null
  content_url: string
  content_view: number | null
  comment_num: number | null
  content_time: string
}

interface GroupItemsExtractionResult {
  found: boolean
  items: Array<Record<string, unknown>>
}

export function parseSamplePayload(
  payload: unknown,
  pageIndex: number,
  tab: SampleManagementTabKey
): ParsedSampleManagementPage | null {
  const config = TAB_CONFIG[tab]
  const extraction = extractGroupItems(payload)
  const hasMore = readHasMoreFlag(payload)

  if (!extraction.found) {
    return null
  }

  if (extraction.items.length === 0) {
    return {
      rows: [],
      hasMore,
      pageSignature: `empty|${config.sheetName}|${pageIndex}`
    }
  }

  const rows: SampleManagementRow[] = []

  extraction.items.forEach((item, groupIndex) => {
    const groupRecord = readRecordAtPath(item, 'apply_group') ?? item
    const creatorInfo =
      readRecordAtPath(groupRecord, 'creator_info') ||
      readRecordAtPath(item, 'creator_info') ||
      readRecordAtPath(item, 'apply_detail.creator_info') ||
      readRecordAtPath(item, 'apply_deatil.creator_info') ||
      {}

    const creatorId = toText(creatorInfo.creator_id)
    const creatorName = toText(creatorInfo.name)
    const groupId = toText(groupRecord.group_id) || creatorId
    const applyInfos = extractApplyInfos(item)

    applyInfos.forEach((applyInfo, requestIndex) => {
      const requestId = toText(applyInfo.apply_id)
      const commissionRaw =
        toText(applyInfo.commission_rate) ||
        toText(readValueAtPath(applyInfo, 'standard_commission.fixed_commission_rate'))
      const commissionRate = parseCommissionRate(commissionRaw)
      const expiredInMs = toNullableNumber(applyInfo.expired_in)
      const region = toText(applyInfo.region) || toText(groupRecord.region) || toText(creatorInfo.region)

      rows.push({
        crawl_time: new Date().toISOString(),
        tab: config.displayName,
        status: config.status,
        page_index: pageIndex,
        group_index: groupIndex + 1,
        request_index: requestIndex + 1,
        group_id: groupId,
        creator_id: creatorId,
        creator_name: creatorName,
        sample_request_id: requestId,
        product_name: toText(applyInfo.product_title),
        product_id: toText(applyInfo.product_id),
        sku_id: toText(applyInfo.sku_id),
        sku_desc: toText(applyInfo.sku_desc),
        sku_image: toText(applyInfo.sku_image),
        commission_rate: commissionRate,
        commission_rate_text: commissionRate === null ? '' : `${commissionRate}%`,
        region,
        sku_stock: toNullableNumber(applyInfo.sku_stock),
        expired_in_ms: expiredInMs,
        expired_in_text: formatDuration(expiredInMs),
        content_summary: ''
      })
    })
  })

  const pageSignature =
    rows.length > 0
      ? rows.map((row) => `${row.group_id}|${row.sample_request_id || 'none'}`).join('||')
      : `empty_rows|${config.sheetName}|${pageIndex}`

  return {
    rows,
    hasMore,
    pageSignature
  }
}

export function extractPerformanceSummaryItems(
  responses: CapturedJsonResponse[],
  sampleRequestId: string
): SampleManagementContentItem[] {
  const items: SampleManagementContentItem[] = []
  const seenKeys = new Set<string>()

  for (const response of responses) {
    const applyId = readQueryParam(response.url, 'apply_id')
    if (applyId !== sampleRequestId) {
      continue
    }

    const performanceItems = extractPerformanceItems(response.body)
    for (const performanceItem of performanceItems) {
      const contentId = toText(performanceItem.content_id)
      const contentType = toContentTypeText(performanceItem.content_type)
      const key = `${contentType}|${contentId}`
      if (!contentId || seenKeys.has(key)) {
        continue
      }
      seenKeys.add(key)

      const createTime = toNullableNumber(performanceItem.create_time)
      const finishTime = toNullableNumber(performanceItem.finish_time)
      const contentTime =
        finishTime && finishTime > 0
          ? `${formatTimestamp(createTime)} ~ ${formatTimestamp(finishTime)}`
          : formatTimestamp(createTime)

      items.push({
        content_type: contentType,
        content_id: contentId,
        cover_img: toText(performanceItem.cover_img),
        content_title: toText(performanceItem.desc),
        content_like: toNullableNumber(performanceItem.like_num),
        content_order: toNullableNumber(performanceItem.paid_order_num),
        content_url: toText(performanceItem.source_url),
        content_view: toNullableNumber(performanceItem.view_num),
        comment_num: toNullableNumber(performanceItem.comment_num),
        content_time: contentTime
      })
    }
  }

  return items
}

function extractGroupItems(payload: unknown): GroupItemsExtractionResult {
  const candidatePaths = [
    'data.agg_info',
    'data.aggInfo',
    'data.list',
    'data.group_list',
    'data.apply_group_list',
    'data.sample_group_list',
    'data.sample_apply_group_list',
    'data.groups',
    'agg_info',
    'aggInfo',
    'list',
    'group_list',
    'apply_group_list',
    'sample_group_list',
    'sample_apply_group_list'
  ]

  for (const path of candidatePaths) {
    const value = readValueAtPath(payload, path)
    if (Array.isArray(value)) {
      return {
        found: true,
        items: value.filter((entry): entry is Record<string, unknown> => looksLikeGroupRecord(entry))
      }
    }
  }

  const recursiveFound = findGroupRecordArrayRecursively(payload, 0)
  if (recursiveFound.found) {
    return recursiveFound
  }

  if (looksLikeGroupRecord(payload)) {
    return {
      found: true,
      items: [payload as Record<string, unknown>]
    }
  }

  return {
    found: false,
    items: []
  }
}

function extractApplyInfos(item: Record<string, unknown>): Array<Record<string, unknown>> {
  const directArrays = [
    readValueAtPath(item, 'apply_infos'),
    readValueAtPath(item, 'apply_info_list'),
    readValueAtPath(item, 'apply_group.apply_infos')
  ]

  for (const candidate of directArrays) {
    if (Array.isArray(candidate)) {
      return candidate.filter((entry): entry is Record<string, unknown> => isRecord(entry))
    }
  }

  const singleCandidates = [
    readRecordAtPath(item, 'apply_detail.apply_info'),
    readRecordAtPath(item, 'apply_deatil.apply_info')
  ].filter((entry): entry is Record<string, unknown> => isRecord(entry))

  return singleCandidates
}

function findGroupRecordArrayRecursively(value: unknown, depth: number): GroupItemsExtractionResult {
  if (depth > 5) {
    return { found: false, items: [] }
  }

  if (Array.isArray(value)) {
    const items = value.filter((entry): entry is Record<string, unknown> => looksLikeGroupRecord(entry))
    if (items.length > 0) {
      return { found: true, items }
    }
    for (const entry of value) {
      const found = findGroupRecordArrayRecursively(entry, depth + 1)
      if (found.found) return found
    }
    return { found: false, items: [] }
  }

  if (!isRecord(value)) {
    return { found: false, items: [] }
  }

  for (const entry of Object.values(value)) {
    const found = findGroupRecordArrayRecursively(entry, depth + 1)
    if (found.found) return found
  }

  return { found: false, items: [] }
}

function looksLikeGroupRecord(value: unknown): value is Record<string, unknown> {
  if (!isRecord(value)) {
    return false
  }

  return Boolean(
    value.apply_group ||
      value.apply_infos ||
      value.apply_detail ||
      value.apply_deatil ||
      (value.group_id && value.creator_info)
  )
}

function readHasMoreFlag(payload: unknown): boolean | undefined {
  const candidatePaths = ['data.has_more', 'pagination.has_more', 'next_pagination.has_more', 'has_more']
  for (const path of candidatePaths) {
    const value = readValueAtPath(payload, path)
    if (typeof value === 'boolean') {
      return value
    }
  }
  return undefined
}

function extractPerformanceItems(payload: unknown): Array<Record<string, unknown>> {
  const directCandidates = [payload, readValueAtPath(payload, 'data.list'), readValueAtPath(payload, 'list')]
  for (const candidate of directCandidates) {
    if (Array.isArray(candidate)) {
      return candidate.filter((entry): entry is Record<string, unknown> => looksLikePerformanceItem(entry))
    }
  }

  return findPerformanceItemsRecursively(payload, 0)
}

function findPerformanceItemsRecursively(value: unknown, depth: number): Array<Record<string, unknown>> {
  if (depth > 5) {
    return []
  }

  if (Array.isArray(value)) {
    const items = value.filter((entry): entry is Record<string, unknown> => looksLikePerformanceItem(entry))
    if (items.length > 0) {
      return items
    }
    for (const entry of value) {
      const found = findPerformanceItemsRecursively(entry, depth + 1)
      if (found.length > 0) {
        return found
      }
    }
    return []
  }

  if (!isRecord(value)) {
    return []
  }

  for (const entry of Object.values(value)) {
    const found = findPerformanceItemsRecursively(entry, depth + 1)
    if (found.length > 0) {
      return found
    }
  }

  return []
}

function looksLikePerformanceItem(value: unknown): value is Record<string, unknown> {
  if (!isRecord(value)) {
    return false
  }
  return Boolean(value.content_id && value.content_type)
}

function readValueAtPath(source: unknown, path: string): unknown {
  if (!path) return source
  return path.split('.').reduce<unknown>((current, segment) => {
    if (current === null || current === undefined) return undefined
    if (Array.isArray(current) && /^\d+$/.test(segment)) {
      return current[Number(segment)]
    }
    if (typeof current === 'object') {
      return (current as Record<string, unknown>)[segment]
    }
    return undefined
  }, source)
}

function readRecordAtPath(source: unknown, path: string): Record<string, unknown> | null {
  const value = readValueAtPath(source, path)
  return isRecord(value) ? value : null
}

function parseCommissionRate(value: string): number | null {
  const numeric = Number(String(value || '').trim())
  if (!Number.isFinite(numeric)) {
    return null
  }
  return Number((numeric / 100).toFixed(2))
}

function formatDuration(durationMs: number | null): string {
  if (!Number.isFinite(durationMs) || durationMs === null || durationMs < 0) {
    return ''
  }

  const totalSeconds = Math.floor(durationMs / 1000)
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return `${days}天 ${hours}小时 ${minutes}分 ${seconds}秒`
}

function toText(value: unknown): string {
  return String(value ?? '').trim()
}

function toNullableNumber(value: unknown): number | null {
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readQueryParam(url: string, key: string): string {
  try {
    return new URL(url).searchParams.get(key) || ''
  } catch {
    return ''
  }
}

function toContentTypeText(value: unknown): string {
  const numeric = Number(value)
  if (numeric === 1) return 'live'
  if (numeric === 2) return 'video'
  return toText(value)
}

function formatTimestamp(value: number | null): string {
  if (!Number.isFinite(value) || value === null || value <= 0) {
    return ''
  }

  const date = new Date(value)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  const second = String(date.getSeconds()).padStart(2, '0')
  return `${year}-${month}-${day} ${hour}:${minute}:${second}`
}
