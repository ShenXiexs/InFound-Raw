import type {
  CreatorFilterOption,
  CreatorFilterTreeOption,
  OutreachCreatorFilterItemsResult
} from '../api/outreach-task.api'
import type { CreateOutreachTaskFilterOptions, SelectOptionItem } from '../types/outreach-task-form'

const normalizeOptionKey = (value: string): string => String(value || '').replace(/\s+/g, '').toLowerCase()

export const normalizeSelectOption = <T extends string | number | boolean>(
  option: CreatorFilterOption<T>
): SelectOptionItem<T> => ({
  label: String(option?.label ?? option?.value ?? ''),
  value: option?.value
})

export const dedupeStringOptions = (options: Array<SelectOptionItem<string>>): Array<SelectOptionItem<string>> => {
  const result = new Map<string, SelectOptionItem<string>>()
  for (const option of options) {
    result.set(normalizeOptionKey(String(option.value)), option)
  }
  return Array.from(result.values())
}

export const flattenTreeOptions = (options: CreatorFilterTreeOption[] | undefined): Array<SelectOptionItem<string>> => {
  if (!Array.isArray(options)) return []

  return options.flatMap((item) => {
    const label = String(item?.label ?? '').trim()
    const rawLabel = String(item?.raw_label ?? '').trim()
    const fallbackLabel = String(item?.value ?? '')
    const current: SelectOptionItem<string> = {
      label: label || rawLabel || fallbackLabel,
      value: String(item?.value ?? '')
    }
    const children = flattenTreeOptions(item?.children)
    return [current, ...children]
  })
}

export const buildTaskFilterOptions = (payload: OutreachCreatorFilterItemsResult): CreateOutreachTaskFilterOptions => {
  const creators = payload.creators?.filters
  const followers = payload.followers?.filters
  const performance = payload.performance?.filters

  return {
    showSearchKeywordFilter: Boolean(creators && Object.prototype.hasOwnProperty.call(creators, 'keyword')),
    showBrandCollaborationFilter: Boolean(
      performance && Object.prototype.hasOwnProperty.call(performance, 'coBranding')
    ),
    productCategoryOptions: flattenTreeOptions(creators?.productCategories?.optionTree),
    avgCommissionRateOptions: creators?.avgCommissionRate?.options?.map(normalizeSelectOption) || [],
    contentTypeOptions: creators?.contentTypes?.options?.map(normalizeSelectOption) || [],
    creatorAgencyOptions: creators?.creatorAgency?.options?.map(normalizeSelectOption) || [],
    fastGrowingOptions: creators?.fastGrowing?.options?.map(normalizeSelectOption) || [],
    notInvitedInPast90DaysOptions: creators?.notInvitedInPast90Days?.options?.map(normalizeSelectOption) || [],
    followerAgeOptions: dedupeStringOptions(followers?.fansAgeRange?.options?.map(normalizeSelectOption) || []),
    followerGenderOptions: followers?.fansGender?.options?.map(normalizeSelectOption) || [],
    followerCountPresetOptions: followers?.fansCountRange?.presetOptions?.map(normalizeSelectOption) || [],
    gmvOptions: performance?.gmvRange?.options?.map(normalizeSelectOption) || [],
    itemsSoldOptions: performance?.salesCountRange?.options?.map(normalizeSelectOption) || [],
    avgVideoViewsPresetOptions: performance?.minAvgVideoViews?.presetOptions?.map(normalizeSelectOption) || [],
    avgLiveViewsPresetOptions: performance?.minAvgLiveViews?.presetOptions?.map(normalizeSelectOption) || [],
    engagementRatePresetOptions: performance?.minEngagementRate?.presetOptions?.map(normalizeSelectOption) || [],
    // GET /outreach/creator-filter-items → performance.filters.estPostRate.options（预计发布率）
    estPostRateOptions: performance?.estPostRate?.options?.map(normalizeSelectOption) || [],
    sortOptions: performance?.sortBy?.options?.map(normalizeSelectOption) || [],
    avgVideoViewsToggleLabel: String(performance?.minAvgVideoViews?.toggleOptionItems?.[0]?.label || ''),
    avgLiveViewsToggleLabel: String(
      performance?.minAvgLiveViews?.toggleOptionItems?.[1]?.label ||
        performance?.minAvgLiveViews?.toggleOptionItems?.[0]?.label ||
        ''
    ),
    engagementRateToggleLabel: String(performance?.minEngagementRate?.toggleOptionItems?.[0]?.label || '')
  }
}
