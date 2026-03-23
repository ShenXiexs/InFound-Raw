import type { SampleManagementPayload, SampleManagementPayloadInput, SampleManagementTabKey } from '@sim-common/types/rpa-sample-management'
import { SAMPLE_MANAGEMENT_TAB_KEYS, TAB_CONFIG } from './config'

const SAMPLE_MANAGEMENT_TAB_ALIASES = new Map<string, SampleManagementTabKey>([
  ['to_review', 'to_review'],
  ['to review', 'to_review'],
  ['review', 'to_review'],
  ['ready_to_ship', 'ready_to_ship'],
  ['ready to ship', 'ready_to_ship'],
  ['shipped', 'shipped'],
  ['in_progress', 'in_progress'],
  ['in progress', 'in_progress'],
  ['completed', 'completed']
])

const normalizeSingleTab = (value: string): SampleManagementTabKey => {
  const normalized = String(value || '')
    .trim()
    .toLowerCase()
  const matched = SAMPLE_MANAGEMENT_TAB_ALIASES.get(normalized)
  if (!matched) {
    throw new Error(`未知样品管理 tab: ${value}`)
  }
  return matched
}

export const createDefaultSampleManagementPayload = (): SampleManagementPayload => ({
  tabs: [...SAMPLE_MANAGEMENT_TAB_KEYS]
})

export const mergeSampleManagementPayload = (input?: SampleManagementPayloadInput): SampleManagementPayload => {
  const rawTabs =
    Array.isArray(input?.tabs) && input?.tabs.length > 0
      ? input.tabs
      : input?.tab
        ? [input.tab]
        : []

  if (rawTabs.length === 0) {
    return createDefaultSampleManagementPayload()
  }

  const seen = new Set<SampleManagementTabKey>()
  const tabs: SampleManagementTabKey[] = []

  rawTabs.forEach((rawTab) => {
    const tab = normalizeSingleTab(rawTab)
    if (!seen.has(tab)) {
      seen.add(tab)
      tabs.push(tab)
    }
  })

  return {
    tabs
  }
}

export const isSampleManagementPayloadInput = (value: unknown): value is SampleManagementPayloadInput => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  return 'tab' in (value as Record<string, unknown>) || 'tabs' in (value as Record<string, unknown>)
}

export const describeSampleManagementTabs = (tabs: SampleManagementTabKey[]): string =>
  tabs.map((tab) => TAB_CONFIG[tab].displayName).join(' + ')
