export type OutreachCreatorType = 'ALL' | 'NEW_ONLY' | 'NEW_AND_NOT_REPLIED'

export interface SelectOptionItem<T = string | number | boolean> {
  label: string
  value: T
}

export interface CreateOutreachTaskFilterOptions {
  /** creators.filters 中存在 keyword 字段时展示搜索关键词并提交 */
  showSearchKeywordFilter?: boolean
  /** performance.filters 中存在 coBranding 字段时展示品牌合作并提交 */
  showBrandCollaborationFilter?: boolean
  productCategoryOptions?: Array<SelectOptionItem<string>>
  avgCommissionRateOptions?: Array<SelectOptionItem<string>>
  contentTypeOptions?: Array<SelectOptionItem<string>>
  creatorAgencyOptions?: Array<SelectOptionItem<string>>
  fastGrowingOptions?: Array<SelectOptionItem<boolean>>
  notInvitedInPast90DaysOptions?: Array<SelectOptionItem<boolean>>
  followerAgeOptions?: Array<SelectOptionItem<string>>
  followerGenderOptions?: Array<SelectOptionItem<string>>
  followerCountPresetOptions?: Array<SelectOptionItem<string>>
  gmvOptions?: Array<SelectOptionItem<string>>
  itemsSoldOptions?: Array<SelectOptionItem<string>>
  avgVideoViewsPresetOptions?: Array<SelectOptionItem<string>>
  avgLiveViewsPresetOptions?: Array<SelectOptionItem<string>>
  engagementRatePresetOptions?: Array<SelectOptionItem<string>>
  estPostRateOptions?: Array<SelectOptionItem<string>>
  sortOptions?: Array<SelectOptionItem<string | number>>
  avgVideoViewsToggleLabel?: string
  avgLiveViewsToggleLabel?: string
  engagementRateToggleLabel?: string
}
