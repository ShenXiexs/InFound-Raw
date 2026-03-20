import type { SellerRpaTaskContextInput } from './seller-rpa-report'

export type AvgCommissionRateOption =
  | 'All'
  | 'Less than 20%'
  | 'Less than 15%'
  | 'Less than 10%'
  | 'Less than 5%'

export type ContentTypeOption = 'All' | 'Video' | 'LIVE'

export type CreatorAgencyOption =
  | 'All'
  | 'Managed by Agency'
  | 'Independent creators'

export type FollowerAgeOption =
  | '18 - 24'
  | '25 - 34'
  | '35 - 44'
  | '45 - 54'
  | '55+'

export type FollowerGenderOption = 'All' | 'Female' | 'Male'

export type PerformanceGmvOption =
  | 'MX$0-MX$100'
  | 'MX$100-MX$1K'
  | 'MX$1K-MX$10K'
  | 'MX$10K+'

export type PerformanceItemsSoldOption = '0-10' | '10-100' | '100-1K' | '1K+'

export type PerformanceEstPostRateOption = 'All' | 'OK' | 'Good' | 'Better'

export interface CreatorFilterConfig {
  productCategorySelections: string[]
  avgCommissionRate: AvgCommissionRateOption
  contentType: ContentTypeOption
  creatorAgency: CreatorAgencyOption
  spotlightCreator: boolean
  fastGrowing: boolean
  notInvitedInPast90Days: boolean
}

export interface FollowerFilterConfig {
  followerAgeSelections: FollowerAgeOption[]
  followerGender: FollowerGenderOption
  followerCountMin: string
  followerCountMax: string
}

export interface PerformanceFilterConfig {
  gmvSelections: PerformanceGmvOption[]
  itemsSoldSelections: PerformanceItemsSoldOption[]
  averageViewsPerVideoMin: string
  averageViewsPerVideoShoppableVideosOnly: boolean
  averageViewersPerLiveMin: string
  averageViewersPerLiveShoppableLiveOnly: boolean
  engagementRateMinPercent: string
  engagementRateShoppableVideosOnly: boolean
  estPostRate: PerformanceEstPostRateOption
  brandCollaborationSelections: string[]
}

export interface OutreachFilterConfig {
  creatorFilters: CreatorFilterConfig
  followerFilters: FollowerFilterConfig
  performanceFilters: PerformanceFilterConfig
  searchKeyword: string
}

export interface OutreachFilterConfigInput extends SellerRpaTaskContextInput {
  creatorFilters?: Partial<CreatorFilterConfig>
  followerFilters?: Partial<FollowerFilterConfig>
  performanceFilters?: Partial<PerformanceFilterConfig>
  searchKeyword?: string
  message?: string
  firstMessage?: string
  secondMessage?: string
  messageSendStrategy?: number | string
  expectCount?: number | string
}
