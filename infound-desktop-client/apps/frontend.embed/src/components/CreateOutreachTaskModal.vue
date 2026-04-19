<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { NButton, NCard, NCheckbox, NDatePicker, NInput, NModal, NSelect, NTabPane, NTabs, NTag, type SelectOption } from 'naive-ui'
import { type OutreachCreatorType } from '../constants/outreach-task-display'
import FilterFieldLabel from './FilterFieldLabel.vue'
export interface SelectOptionItem<T = string | number> {
  label: string
  value: T
}

export interface CreateOutreachTaskFilterOptions {
  productCategoryOptions?: Array<SelectOptionItem<string>>
  avgCommissionRateOptions?: Array<SelectOptionItem<string>>
  contentTypeOptions?: Array<SelectOptionItem<string>>
  creatorAgencyOptions?: Array<SelectOptionItem<string>>
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

interface MessageTemplateForm {
  content: string
  enableProductMessage: boolean
  productIds: string[]
  productInput: string
}

interface CreateOutreachTaskFormState {
  taskName: string
  startTime: string
  planCount: string
  searchKeyword: string
  creatorSort: string | number
  outreachCreatorType: OutreachCreatorType
  creatorFilters: {
    productCategorySelections: string[]
    avgCommissionRate: string
    contentType: string
    creatorAgency: string
    spotlightCreator: boolean
    fastGrowing: boolean
    notInvitedInPast90Days: boolean
  }
  followerFilters: {
    followerAgeSelections: string[]
    followerGender: string
    followerCountMin: string
    followerCountMax: string
  }
  performanceFilters: {
    gmvSelections: string[]
    itemsSoldSelections: string[]
    averageViewsPerVideoMin: string
    averageViewsPerVideoShoppableVideosOnly: boolean
    averageViewersPerLiveMin: string
    averageViewersPerLiveShoppableLiveOnly: boolean
    engagementRateMinPercent: string
    engagementRateShoppableVideosOnly: boolean
    estPostRate: string
    brandCollaborationInput: string
  }
  firstMessage: MessageTemplateForm
  replyMessage: MessageTemplateForm
}

export interface CreateOutreachTaskFormPayload {
  taskName: string
  startTime?: string
  planCount: number
  creatorSort: string | number
  outreachCreatorType: OutreachCreatorType
  filterConfig: {
    creatorFilters: {
      productCategorySelections: string[]
      avgCommissionRate: string
      contentType: string
      creatorAgency: string
      spotlightCreator: boolean
      fastGrowing: boolean
      notInvitedInPast90Days: boolean
    }
    followerFilters: {
      followerAgeSelections: string[]
      followerGender: string
      followerCountMin: string
      followerCountMax: string
    }
    performanceFilters: {
      gmvSelections: string[]
      itemsSoldSelections: string[]
      averageViewsPerVideoMin: string
      averageViewsPerVideoShoppableVideosOnly: boolean
      averageViewersPerLiveMin: string
      averageViewersPerLiveShoppableLiveOnly: boolean
      engagementRateMinPercent: string
      engagementRateShoppableVideosOnly: boolean
      estPostRate: string
      brandCollaborationSelections: string[]
    }
    searchKeyword: string
  }
  messageTemplate: {
    firstMessage: {
      content: string
      productMessageEnabled: boolean
      productIds: string[]
    }
    replyMessage?: {
      content: string
      productMessageEnabled: boolean
      productIds: string[]
    }
  }
}

const props = withDefaults(
  defineProps<{
    visible: boolean
    saving?: boolean
    submitError?: string
    maxPlanCount?: number
    mode?: 'modal' | 'page'
    title?: string
    showClose?: boolean
    initialData?: Partial<CreateOutreachTaskFormPayload>
    filterOptions?: CreateOutreachTaskFilterOptions
  }>(),
  {
    saving: false,
    submitError: '',
    maxPlanCount: 200,
    mode: 'modal',
    title: '新建任务',
    showClose: true
  }
)

const emit = defineEmits<{
  (event: 'submit', payload: CreateOutreachTaskFormPayload): void
  (event: 'cancel'): void
  (event: 'dirty-change', value: boolean): void
}>()

const toSelectOptions = (items: string[]): Array<{ label: string; value: string }> => {
  return items.map((item) => ({ label: item, value: item }))
}

const PRODUCT_CATEGORY_OPTIONS: Array<{ label: string; value: string }> = [
  { label: 'Home Supplies', value: '600001' },
  { label: 'Kitchenware', value: '600024' },
  { label: 'Textiles & Soft Furnishings', value: '600154' },
  { label: 'Household Appliances', value: '600942' },
  { label: 'Womenswear & Underwear', value: '601152' },
  { label: 'Shoes', value: '601352' },
  { label: 'Beauty & Personal Care', value: '601450' },
  { label: 'Phones & Electronics', value: '601739' },
  { label: 'Computers & Office Equipment', value: '601755' },
  { label: 'Pet Supplies', value: '602118' },
  { label: 'Sports & Outdoor', value: '603014' },
  { label: 'Toys & Hobbies', value: '604206' },
  { label: 'Furniture', value: '604453' },
  { label: 'Tools & Hardware', value: '604579' },
  { label: 'Home Improvement', value: '604968' },
  { label: 'Automotive & Motorcycle', value: '605196' },
  { label: 'Fashion Accessories', value: '605248' },
  { label: 'Health', value: '700645' },
  { label: 'Books, Magazines & Audio', value: '801928' },
  { label: "Kids' Fashion", value: '802184' },
  { label: 'Menswear & Underwear', value: '824328' },
  { label: 'Luggage & Bags', value: '824584' },
  { label: 'Collectibles', value: '951432' },
  { label: 'Jewelry Accessories & Derivatives', value: '953224' }
]
const AVG_COMMISSION_RATE_OPTIONS = ['All', 'Less than 20%', 'Less than 15%', 'Less than 10%', 'Less than 5%']
const CONTENT_TYPE_OPTIONS = ['All', 'Video', 'LIVE']
const CREATOR_AGENCY_OPTIONS = ['All', 'Managed by Agency', 'Independent creators']
const FOLLOWER_AGE_OPTIONS = ['18 - 24', '25 - 34', '35 - 44', '45 - 54', '55+']
const FOLLOWER_GENDER_OPTIONS = ['All', 'Female', 'Male']
const FOLLOWER_COUNT_PRESET_OPTIONS = ['0', '10K', '100K', '1M', '10M+']
const PERFORMANCE_GMV_OPTIONS = ['MX$0-MX$100', 'MX$100-MX$1K', 'MX$1K-MX$10K', 'MX$10K+']
const PERFORMANCE_ITEMS_SOLD_OPTIONS = ['0-10', '10-100', '100-1K', '1K+']
const PERFORMANCE_AVG_VIDEO_VIEWS_PRESET_OPTIONS = ['0', '100', '1K', '10K', '100K+']
const PERFORMANCE_AVG_LIVE_VIEWS_PRESET_OPTIONS = ['0', '100', '1K', '10K', '100K+']
const PERFORMANCE_ENGAGEMENT_RATE_PRESET_OPTIONS = ['0', '1', '3', '5', '10+']
const PERFORMANCE_EST_POST_RATE_OPTIONS = ['All', 'OK', 'Good', 'Better']
const AVG_COMMISSION_RATE_SELECT_OPTIONS = toSelectOptions(AVG_COMMISSION_RATE_OPTIONS)
const CONTENT_TYPE_SELECT_OPTIONS = toSelectOptions(CONTENT_TYPE_OPTIONS)
const CREATOR_AGENCY_SELECT_OPTIONS = toSelectOptions(CREATOR_AGENCY_OPTIONS)
const FOLLOWER_AGE_SELECT_OPTIONS = toSelectOptions(FOLLOWER_AGE_OPTIONS)
const FOLLOWER_GENDER_SELECT_OPTIONS = toSelectOptions(FOLLOWER_GENDER_OPTIONS)
const PERFORMANCE_GMV_SELECT_OPTIONS = toSelectOptions(PERFORMANCE_GMV_OPTIONS)
const PERFORMANCE_ITEMS_SOLD_SELECT_OPTIONS = toSelectOptions(PERFORMANCE_ITEMS_SOLD_OPTIONS)
const PERFORMANCE_EST_POST_RATE_SELECT_OPTIONS = toSelectOptions(PERFORMANCE_EST_POST_RATE_OPTIONS)
const SORT_OPTIONS: Array<{ label: string; value: string }> = [
  { label: '官方默认值', value: 'OFFICIAL_DEFAULT' },
  { label: '达人GMV降序', value: 'GMV_DESC' },
  { label: '达人粉丝数降序', value: 'FOLLOWERS_DESC' },
  { label: '达人佣金率降序', value: 'COMMISSION_DESC' }
]
const OUTREACH_CREATOR_OPTIONS: Array<{ label: string; value: OutreachCreatorType }> = [
  { label: '建联所有达人', value: 'ALL' },
  { label: '只建联新达人', value: 'NEW_ONLY' },
  { label: '建联新达人和未回复达人', value: 'NEW_AND_NOT_REPLIED' }
]

const createDefaultMessageTemplate = (): MessageTemplateForm => ({
  content: '',
  enableProductMessage: false,
  productIds: [],
  productInput: ''
})

const createDefaultFormState = (): CreateOutreachTaskFormState => ({
  taskName: '',
  startTime: '',
  planCount: '',
  searchKeyword: '',
  creatorSort: 'OFFICIAL_DEFAULT',
  outreachCreatorType: 'ALL',
  creatorFilters: {
    productCategorySelections: ['600001'],
    avgCommissionRate: 'All',
    contentType: 'All',
    creatorAgency: 'All',
    spotlightCreator: false,
    fastGrowing: false,
    notInvitedInPast90Days: false
  },
  followerFilters: {
    followerAgeSelections: [],
    followerGender: 'All',
    followerCountMin: '0',
    followerCountMax: '10,000,000+'
  },
  performanceFilters: {
    gmvSelections: [],
    itemsSoldSelections: [],
    averageViewsPerVideoMin: '0',
    averageViewsPerVideoShoppableVideosOnly: false,
    averageViewersPerLiveMin: '0',
    averageViewersPerLiveShoppableLiveOnly: false,
    engagementRateMinPercent: '0',
    engagementRateShoppableVideosOnly: false,
    estPostRate: 'All',
    brandCollaborationInput: ''
  },
  firstMessage: createDefaultMessageTemplate(),
  replyMessage: createDefaultMessageTemplate()
})

type MessageSectionType = 'first' | 'reply'
type CreatorFilterTab = 'creator' | 'followers' | 'performance'

const form = ref<CreateOutreachTaskFormState>(createDefaultFormState())
const errors = reactive<Record<string, string>>({})
const activeMessageTab = ref<MessageSectionType>('first')
const activeCreatorFilterTab = ref<CreatorFilterTab>('creator')
const MESSAGE_TAB_OPTIONS: Array<{ label: string; value: MessageSectionType }> = [
  { label: '首次消息', value: 'first' },
  { label: '回复达人消息', value: 'reply' }
]
const CREATOR_FILTER_TAB_OPTIONS: Array<{ label: string; value: CreatorFilterTab }> = [
  { label: '达人', value: 'creator' },
  { label: '粉丝数', value: 'followers' },
  { label: '表现', value: 'performance' }
]
type FilterLabelKey =
  | 'searchKeyword'
  | 'filterConditions'
  | 'productCategory'
  | 'avgCommissionRate'
  | 'contentType'
  | 'creatorAgency'
  | 'spotlightCreator'
  | 'fastGrowing'
  | 'notInvitedInPast90Days'
  | 'followerAge'
  | 'followerGender'
  | 'followerCountMin'
  | 'followerCountMax'
  | 'gmv'
  | 'itemsSold'
  | 'averageViewsPerVideoMin'
  | 'averageViewersPerLiveMin'
  | 'engagementRateMinPercent'
  | 'estPostRate'
  | 'brandCollaborations'

// 需要切回英文时，把这里从 'zh' 改成 'en' 即可。
const FILTER_LABEL_LANG: 'zh' | 'en' = 'zh'
const FILTER_LABELS: Record<FilterLabelKey, { zh: string; en: string }> = {
  searchKeyword: { zh: '搜索关键词', en: 'Search keyword' },
  filterConditions: { zh: '筛选条件', en: 'Filter conditions' },
  productCategory: { zh: '商品类目（多选）', en: 'Product category (multiple)' },
  avgCommissionRate: { zh: '平均佣金率', en: 'Avg. commission rate' },
  contentType: { zh: '内容类型', en: 'Content type' },
  creatorAgency: { zh: '达人机构', en: 'Creator agency' },
  spotlightCreator: { zh: 'Spotlight 达人', en: 'Spotlight Creator' },
  fastGrowing: { zh: '快速成长榜', en: 'Fast growing' },
  notInvitedInPast90Days: { zh: '过去 90 天内未获邀请的达人', en: 'Not invited in past 90 days' },
  followerAge: { zh: '粉丝年龄（多选）', en: 'Follower age (multiple)' },
  followerGender: { zh: '粉丝性别', en: 'Follower gender' },
  followerCountMin: { zh: '粉丝数最小值', en: 'Follower count min' },
  followerCountMax: { zh: '粉丝数最大值', en: 'Follower count max' },
  gmv: { zh: 'GMV（多选）', en: 'GMV (multiple)' },
  itemsSold: { zh: '成交件数（多选）', en: 'Items sold (multiple)' },
  averageViewsPerVideoMin: { zh: '平均每个视频的播放量', en: 'Average views per video min' },
  averageViewersPerLiveMin: { zh: '平均每场直播的观看人数', en: 'Average viewers per LIVE min' },
  engagementRateMinPercent: { zh: '互动率 (%)', en: 'Engagement rate min (%)' },
  estPostRate: { zh: '预计发布率', en: 'Est. post rate' },
  brandCollaborations: { zh: '品牌合作（逗号分隔）', en: 'Brand collaborations (comma separated)' }
}
const getFilterLabel = (key: FilterLabelKey): string => FILTER_LABELS[key][FILTER_LABEL_LANG]

type FilterPlaceholderKey = 'searchKeyword' | 'selectDefault' | 'brandCollaborations'
const FILTER_PLACEHOLDERS: Record<FilterPlaceholderKey, { zh: string; en: string }> = {
  searchKeyword: {
    zh: '搜索姓名、商品、话题标签或关键词',
    en: 'Search name, product, hashtag or keyword'
  },
  selectDefault: { zh: '请选择', en: 'Please select' },
  brandCollaborations: {
    zh: "例如：L'OREAL PROFESSIONNEL, Maybelline New York",
    en: "e.g. L'OREAL PROFESSIONNEL, Maybelline New York"
  }
}
const getFilterPlaceholder = (key: FilterPlaceholderKey): string => FILTER_PLACEHOLDERS[key][FILTER_LABEL_LANG]

const FILTER_TIPS = {
  productCategory:
    '选择一个商品类目，以查看过去 30 天内在该类目中产生成交额或推广商品的达人，或在过去 90 天内将商品添加到商品橱窗的达人。',
  avgCommissionRate: '基于过去 30 天内商品橱窗商品数、销售量和推广商品数的达人平均佣金率范围。',
  contentType: '近 30 天内达人用于推广商品的内容类型，包括短视频或直播。',
  spotlightCreator: '因成长潜力高被 TikTok Shop 选中的达人',
  fastGrowing: '过去 30 天内交易量、成交额、带货视频数、直播观看次数或粉丝数涨幅最高的前 10% 达人。',
  notInvitedInPast90Days: '选择此筛选条件可查看你在过去 90 天内尚未邀请过的达人。',
  gmv: '过去 30 天内达人通过直播、带货视频或商品橱窗产生的成交额。',
  itemsSold: '过去 30 天内达人通过直播、带货视频或商品橱窗产生的成交件数。',
  engagementRateMinPercent: '过去 30 天内帖子互动（点赞、分享和评论）数量除以视频的平均播放总量。',
  estPostRate: '这些类别表示达人在收到样品后发布带货视频或直播的频率。',
  brandCollaborations: '过去 30 天内达人通过带货视频、商品橱窗或直播进行推广和销售的品牌。'
} as const

/** 为 false 时隐藏「Spotlight 达人」勾选项；表单字段、中英文 label 与问号提示已接好，需要展示时改为 true。 */
const SHOW_SPOTLIGHT_CREATOR_FILTER = false

const initialSnapshot = ref('')
const formContainerRef = ref<HTMLElement | null>(null)

const isAllCreatorMode = computed(() => form.value.outreachCreatorType === 'ALL')
const messageTip = computed(() =>
  isAllCreatorMode.value ? '建联时发送首次消息；达人回复后，发送回复达人消息' : '建联时发送首次消息'
)
const productCategoryOptions = computed<SelectOption[]>(() =>
  (props.filterOptions?.productCategoryOptions?.length ? props.filterOptions.productCategoryOptions : PRODUCT_CATEGORY_OPTIONS) as SelectOption[]
)
const avgCommissionRateOptions = computed<SelectOption[]>(() =>
  (props.filterOptions?.avgCommissionRateOptions?.length ? props.filterOptions.avgCommissionRateOptions : AVG_COMMISSION_RATE_SELECT_OPTIONS) as SelectOption[]
)
const contentTypeOptions = computed<SelectOption[]>(() =>
  (props.filterOptions?.contentTypeOptions?.length ? props.filterOptions.contentTypeOptions : CONTENT_TYPE_SELECT_OPTIONS) as SelectOption[]
)
const creatorAgencyOptions = computed<SelectOption[]>(() =>
  (props.filterOptions?.creatorAgencyOptions?.length ? props.filterOptions.creatorAgencyOptions : CREATOR_AGENCY_SELECT_OPTIONS) as SelectOption[]
)
const followerAgeOptions = computed<SelectOption[]>(() =>
  (props.filterOptions?.followerAgeOptions?.length ? props.filterOptions.followerAgeOptions : FOLLOWER_AGE_SELECT_OPTIONS) as SelectOption[]
)
const followerGenderOptions = computed<SelectOption[]>(() =>
  (props.filterOptions?.followerGenderOptions?.length ? props.filterOptions.followerGenderOptions : FOLLOWER_GENDER_SELECT_OPTIONS) as SelectOption[]
)
const followerCountPresetOptions = computed<SelectOption[]>(() =>
  (
    props.filterOptions?.followerCountPresetOptions?.length
      ? props.filterOptions.followerCountPresetOptions
      : toSelectOptions(FOLLOWER_COUNT_PRESET_OPTIONS)
  ) as SelectOption[]
)
const gmvOptions = computed<SelectOption[]>(() =>
  (props.filterOptions?.gmvOptions?.length ? props.filterOptions.gmvOptions : PERFORMANCE_GMV_SELECT_OPTIONS) as SelectOption[]
)
const itemsSoldOptions = computed<SelectOption[]>(() =>
  (props.filterOptions?.itemsSoldOptions?.length ? props.filterOptions.itemsSoldOptions : PERFORMANCE_ITEMS_SOLD_SELECT_OPTIONS) as SelectOption[]
)
const avgVideoViewsPresetOptions = computed<SelectOption[]>(() =>
  (
    props.filterOptions?.avgVideoViewsPresetOptions?.length
      ? props.filterOptions.avgVideoViewsPresetOptions
      : toSelectOptions(PERFORMANCE_AVG_VIDEO_VIEWS_PRESET_OPTIONS)
  ) as SelectOption[]
)
const avgLiveViewsPresetOptions = computed<SelectOption[]>(() =>
  (
    props.filterOptions?.avgLiveViewsPresetOptions?.length
      ? props.filterOptions.avgLiveViewsPresetOptions
      : toSelectOptions(PERFORMANCE_AVG_LIVE_VIEWS_PRESET_OPTIONS)
  ) as SelectOption[]
)
const engagementRatePresetOptions = computed<SelectOption[]>(() =>
  (
    props.filterOptions?.engagementRatePresetOptions?.length
      ? props.filterOptions.engagementRatePresetOptions
      : toSelectOptions(PERFORMANCE_ENGAGEMENT_RATE_PRESET_OPTIONS)
  ) as SelectOption[]
)
const estPostRateOptions = computed<SelectOption[]>(() =>
  (props.filterOptions?.estPostRateOptions?.length ? props.filterOptions.estPostRateOptions : PERFORMANCE_EST_POST_RATE_SELECT_OPTIONS) as SelectOption[]
)
const sortOptions = computed<SelectOption[]>(() =>
  (props.filterOptions?.sortOptions?.length ? props.filterOptions.sortOptions : SORT_OPTIONS) as SelectOption[]
)
// 暂未接入后端字段，相关控件先隐藏保留
// const avgVideoViewsToggleLabel = computed(() => props.filterOptions?.avgVideoViewsToggleLabel || 'Filter by shoppable videos（Average views per video）')
// const avgLiveViewsToggleLabel = computed(() => props.filterOptions?.avgLiveViewsToggleLabel || 'Filter by shoppable LIVE streams')
// const engagementRateToggleLabel = computed(() => props.filterOptions?.engagementRateToggleLabel || 'Filter by shoppable videos（Engagement）')
const ERROR_SCROLL_ORDER = [
  'taskName',
  'startTime',
  'planCount',
  'outreachCreatorType',
  'firstMessageContent',
  'firstProductIds',
  'replyMessageContent',
  'replyProductIds'
] as const

const setError = (key: string, message: string): void => {
  errors[key] = message
}

const clearError = (key: string): void => {
  delete errors[key]
}

const clearErrors = (): void => {
  for (const key of Object.keys(errors)) {
    delete errors[key]
  }
}

const getCurrentMinute = (): Date => {
  const current = new Date()
  current.setSeconds(0, 0)
  return current
}

const pad2 = (value: number): string => String(value).padStart(2, '0')

const formatDateTimeLocal = (date: Date): string => {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}T${pad2(date.getHours())}:${pad2(date.getMinutes())}`
}

const toTimestamp = (value: string): number | null => {
  const normalized = toDateTimeLocal(value)
  if (!normalized) return null
  const parsed = new Date(normalized)
  const timestamp = parsed.getTime()
  return Number.isNaN(timestamp) ? null : timestamp
}

const fromTimestamp = (value: number | null): string => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return ''
  return formatDateTimeLocal(new Date(value))
}

const startTimeValue = computed<number | null>(() => toTimestamp(form.value.startTime))

const isStartDateDisabled = (timestamp: number): boolean => {
  const candidate = new Date(timestamp)
  candidate.setHours(0, 0, 0, 0)
  const today = getCurrentMinute()
  today.setHours(0, 0, 0, 0)
  return candidate.getTime() < today.getTime()
}

const handleStartTimeChange = (value: number | null): void => {
  form.value.startTime = fromTimestamp(value)
  if (!form.value.startTime || validateStartTime(form.value.startTime)) {
    clearError('startTime')
    return
  }

  setError('startTime', '启动时间已过期，请重新设置启动时间')
}

const normalizeDateTimeForSubmit = (value: string): string => {
  if (!value) return ''
  if (value.length === 16) {
    return `${value.replace('T', ' ')}:00`
  }
  return value.replace('T', ' ')
}

const splitInputTokens = (value: string): string[] => {
  return value
    .split(/[\s,，]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

const normalizeListByComma = (value: string): string[] => {
  return value
    .split(/[\n,，]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

const getMessageTemplate = (type: MessageSectionType): MessageTemplateForm => {
  return type === 'first' ? form.value.firstMessage : form.value.replyMessage
}

const toDateTimeLocal = (value: string): string => {
  const token = String(value || '').trim()
  if (!token) return ''
  const normalized = token.replace(' ', 'T')
  return normalized.length >= 16 ? normalized.slice(0, 16) : normalized
}

const applyInitialData = (initialData?: Partial<CreateOutreachTaskFormPayload>): void => {
  const nextState = createDefaultFormState()
  if (!initialData) {
    form.value = nextState
    return
  }

  if (typeof initialData.taskName === 'string') nextState.taskName = initialData.taskName
  if (typeof initialData.startTime === 'string') nextState.startTime = toDateTimeLocal(initialData.startTime)
  if (typeof initialData.planCount === 'number' && Number.isFinite(initialData.planCount)) {
    nextState.planCount = String(initialData.planCount)
  }
  if (typeof initialData.creatorSort === 'string' || typeof initialData.creatorSort === 'number') nextState.creatorSort = initialData.creatorSort
  if (initialData.outreachCreatorType) nextState.outreachCreatorType = initialData.outreachCreatorType

  const filterConfig = initialData.filterConfig
  if (filterConfig) {
    if (typeof filterConfig.searchKeyword === 'string') nextState.searchKeyword = filterConfig.searchKeyword
    if (filterConfig.creatorFilters) {
      nextState.creatorFilters = {
        ...nextState.creatorFilters,
        ...filterConfig.creatorFilters,
        productCategorySelections: [...(filterConfig.creatorFilters.productCategorySelections || nextState.creatorFilters.productCategorySelections)]
      }
    }
    if (filterConfig.followerFilters) {
      nextState.followerFilters = {
        ...nextState.followerFilters,
        ...filterConfig.followerFilters,
        followerAgeSelections: [...(filterConfig.followerFilters.followerAgeSelections || nextState.followerFilters.followerAgeSelections)]
      }
    }
    if (filterConfig.performanceFilters) {
      nextState.performanceFilters = {
        ...nextState.performanceFilters,
        ...filterConfig.performanceFilters,
        gmvSelections: [...(filterConfig.performanceFilters.gmvSelections || nextState.performanceFilters.gmvSelections)],
        itemsSoldSelections: [...(filterConfig.performanceFilters.itemsSoldSelections || nextState.performanceFilters.itemsSoldSelections)],
        brandCollaborationInput: (filterConfig.performanceFilters.brandCollaborationSelections || []).join(', ')
      }
    }
  }

  const messageTemplate = initialData.messageTemplate
  if (messageTemplate?.firstMessage) {
    nextState.firstMessage.content = messageTemplate.firstMessage.content || ''
    nextState.firstMessage.enableProductMessage = Boolean(messageTemplate.firstMessage.productMessageEnabled)
    nextState.firstMessage.productIds = [...(messageTemplate.firstMessage.productIds || [])]
  }
  if (messageTemplate?.replyMessage) {
    nextState.replyMessage.content = messageTemplate.replyMessage.content || ''
    nextState.replyMessage.enableProductMessage = Boolean(messageTemplate.replyMessage.productMessageEnabled)
    nextState.replyMessage.productIds = [...(messageTemplate.replyMessage.productIds || [])]
  }

  form.value = nextState
}

const getProductIdErrorKey = (type: MessageSectionType): string => {
  return type === 'first' ? 'firstProductIds' : 'replyProductIds'
}

const getMessageContentErrorKey = (type: MessageSectionType): string => {
  return type === 'first' ? 'firstMessageContent' : 'replyMessageContent'
}

const appendMessageProductIds = (type: MessageSectionType, rawValue: string): void => {
  const message = getMessageTemplate(type)
  const tokens = splitInputTokens(rawValue)
  if (tokens.length === 0) {
    message.productInput = ''
    return
  }

  const nextIds = [...message.productIds]
  const seen = new Set(nextIds)

  for (const token of tokens) {
    if (seen.has(token)) continue
    if (nextIds.length >= 4) {
      setError(getProductIdErrorKey(type), '商品ID最多可填写4个')
      break
    }
    seen.add(token)
    nextIds.push(token)
  }

  message.productIds = nextIds
  message.productInput = ''

  if (nextIds.length > 0 && nextIds.length <= 4) {
    clearError(getProductIdErrorKey(type))
  }
}

const removeMessageProductId = (type: MessageSectionType, targetId: string): void => {
  const message = getMessageTemplate(type)
  message.productIds = message.productIds.filter((item) => item !== targetId)

  if (message.productIds.length > 0) {
    clearError(getProductIdErrorKey(type))
  }
}

const flushMessageProductInput = (type: MessageSectionType): void => {
  const message = getMessageTemplate(type)
  appendMessageProductIds(type, message.productInput)
}

const handleProductInputKeydown = (event: KeyboardEvent, type: MessageSectionType): void => {
  if (event.key === 'Enter' || event.key === ',' || event.key === '，') {
    event.preventDefault()
    flushMessageProductInput(type)
  }
}

const handleProductMessageToggle = (type: MessageSectionType): void => {
  const message = getMessageTemplate(type)
  if (message.enableProductMessage) return

  message.productIds = []
  message.productInput = ''
  clearError(getProductIdErrorKey(type))
}

const initializeForm = (): void => {
  applyInitialData(props.initialData)
  if (!sortOptions.value.some((item) => item.value === form.value.creatorSort) && sortOptions.value.length > 0) {
    form.value.creatorSort = sortOptions.value[0]?.value ?? form.value.creatorSort
  }
  activeCreatorFilterTab.value = 'creator'
  activeMessageTab.value = 'first'
  clearErrors()
  initialSnapshot.value = JSON.stringify(form.value)
  emit('dirty-change', false)
}

const resetForm = (): void => {
  form.value = createDefaultFormState()
  activeCreatorFilterTab.value = 'creator'
  activeMessageTab.value = 'first'
  clearErrors()
  initialSnapshot.value = JSON.stringify(form.value)
  emit('dirty-change', false)
}

const closeModal = (): void => {
  if (props.saving) return
  emit('cancel')
}

const handleModalShowChange = (value: boolean): void => {
  if (!value && props.visible) {
    closeModal()
  }
}

const validateStartTime = (value: string): boolean => {
  if (!value) return true
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return false
  parsed.setSeconds(0, 0)
  const currentMinute = getCurrentMinute()
  return parsed.getTime() > currentMinute.getTime()
}

const validateMessageTemplate = (type: MessageSectionType): void => {
  const message = getMessageTemplate(type)
  const trimmedContent = message.content.trim()

  if (!trimmedContent) {
    setError(getMessageContentErrorKey(type), type === 'first' ? '请填写首次消息模板' : '请填写回复达人消息模板')
  } else if (trimmedContent.length > 2000) {
    setError(getMessageContentErrorKey(type), '消息模板不能超过2000字')
  }

  if (!message.enableProductMessage) return

  flushMessageProductInput(type)
  if (message.productIds.length === 0) {
    setError(getProductIdErrorKey(type), '勾选商品消息后，请至少填写1个商品ID')
  } else if (message.productIds.length > 4) {
    setError(getProductIdErrorKey(type), '商品ID最多可填写4个')
  }
}

const validateForm = (): boolean => {
  clearErrors()

  const state = form.value
  state.taskName = state.taskName.trim()

  if (!state.taskName) {
    setError('taskName', '请输入任务名称')
  } else if (state.taskName.length > 120) {
    setError('taskName', '任务名称不能超过120字')
  }

  if (state.startTime && !validateStartTime(state.startTime)) {
    setError('startTime', '启动时间已过期，请重新设置启动时间')
  }

  const planCountRaw = state.planCount.trim()
  const planCount = Number(planCountRaw)
  if (!planCountRaw) {
    setError('planCount', '请输入建联人数')
  } else if (!Number.isInteger(planCount) || planCount <= 0) {
    setError('planCount', '建联人数需要为大于0的整数')
  } else if (planCount > props.maxPlanCount) {
    setError('planCount', `建联人数不能超过 ${props.maxPlanCount}`)
  }

  if (!state.outreachCreatorType) {
    setError('outreachCreatorType', '请选择建联达人')
  }

  validateMessageTemplate('first')
  if (isAllCreatorMode.value) {
    validateMessageTemplate('reply')
  }

  return Object.keys(errors).length === 0
}

const getFirstErrorKey = (): string | undefined => {
  for (const key of ERROR_SCROLL_ORDER) {
    if (errors[key]) {
      return key
    }
  }
  return Object.keys(errors)[0]
}

const scrollToFirstError = async (): Promise<void> => {
  const firstErrorKey = getFirstErrorKey()
  if (!firstErrorKey) return

  if (firstErrorKey.startsWith('reply')) {
    activeMessageTab.value = 'reply'
  } else if (firstErrorKey.startsWith('first')) {
    activeMessageTab.value = 'first'
  }

  await nextTick()

  const target = formContainerRef.value?.querySelector<HTMLElement>(`[data-error-key="${firstErrorKey}"]`)
  if (!target) return

  target.scrollIntoView({
    behavior: 'smooth',
    block: 'center'
  })

  const focusTarget =
    target.querySelector<HTMLElement>('input, textarea, button, [tabindex]:not([tabindex="-1"])') ??
    target

  window.setTimeout(() => {
    focusTarget.focus?.({ preventScroll: true })
  }, 120)
}

const buildPayload = (): CreateOutreachTaskFormPayload => {
  const state = form.value
  const brandCollaborationSelections = normalizeListByComma(state.performanceFilters.brandCollaborationInput)

  return {
    taskName: state.taskName.trim(),
    startTime: state.startTime ? normalizeDateTimeForSubmit(state.startTime) : undefined,
    planCount: Number(state.planCount),
    creatorSort: state.creatorSort,
    outreachCreatorType: state.outreachCreatorType,
    filterConfig: {
      creatorFilters: {
        ...state.creatorFilters,
        productCategorySelections: [...state.creatorFilters.productCategorySelections]
      },
      followerFilters: {
        ...state.followerFilters,
        followerAgeSelections: [...state.followerFilters.followerAgeSelections]
      },
      performanceFilters: {
        ...state.performanceFilters,
        gmvSelections: [...state.performanceFilters.gmvSelections],
        itemsSoldSelections: [...state.performanceFilters.itemsSoldSelections],
        brandCollaborationSelections
      },
      searchKeyword: state.searchKeyword.trim()
    },
    messageTemplate: {
      firstMessage: {
        content: state.firstMessage.content.trim(),
        productMessageEnabled: state.firstMessage.enableProductMessage,
        productIds: [...state.firstMessage.productIds]
      },
      replyMessage: isAllCreatorMode.value
        ? {
            content: state.replyMessage.content.trim(),
            productMessageEnabled: state.replyMessage.enableProductMessage,
            productIds: [...state.replyMessage.productIds]
          }
        : undefined
    }
  }
}

const handleSubmit = (): void => {
  if (!validateForm()) {
    void scrollToFirstError()
    return
  }
  emit('submit', buildPayload())
}

watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      initializeForm()
    }
  },
  { immediate: true }
)

watch(
  () => props.initialData,
  () => {
    if (props.visible) {
      initializeForm()
    }
  },
  { deep: true }
)

watch(
  () => props.filterOptions,
  () => {
    if (!sortOptions.value.some((item) => item.value === form.value.creatorSort) && sortOptions.value.length > 0) {
      form.value.creatorSort = sortOptions.value[0]?.value ?? form.value.creatorSort
    }
  },
  { deep: true }
)

watch(
  () => form.value.outreachCreatorType,
  (value) => {
    if (value !== 'ALL') {
      activeMessageTab.value = 'first'
      clearError('replyMessageContent')
      clearError('replyProductIds')
    }
  }
)

watch(
  form,
  () => {
    const currentSnapshot = JSON.stringify(form.value)
    emit('dirty-change', currentSnapshot !== initialSnapshot.value)
  },
  { deep: true }
)
</script>

<template>
  <NModal
    :show="visible"
    :mask-closable="!saving"
    :close-on-esc="!saving"
    transform-origin="center"
    @update:show="handleModalShowChange"
  >
    <NCard
      class="modal-card"
      :bordered="false"
      content-style="padding: 0; display: flex; flex-direction: column; min-height: 0; overflow: hidden;"
      role="dialog"
      size="small"
    >
      <header class="modal-header">
        <h2>{{ title }}</h2>
        <NButton v-if="showClose" quaternary circle class="close-btn" :disabled="saving" @click="closeModal">
          <span class="close-symbol">×</span>
        </NButton>
      </header>

      <div ref="formContainerRef" class="modal-body">
        <p v-if="submitError" class="submit-error">{{ submitError }}</p>

        <section class="form-block" data-error-key="taskName">
          <label class="field-label" for="create-task-name">1. 任务名称</label>
          <NInput
            id="create-task-name"
            v-model:value="form.taskName"
            class="field-input"
            maxlength="120"
            placeholder="请输入任务名称"
            type="text"
            @blur="form.taskName = form.taskName.trim()"
          />
          <div class="field-helper">
            <span>120字内，去前后空格，必填</span>
            <span>{{ form.taskName.length }}/120</span>
          </div>
          <p v-if="errors.taskName" class="field-error">{{ errors.taskName }}</p>
        </section>

        <section class="form-block" data-error-key="startTime">
          <label class="field-label" for="create-task-start-time">2. 启动时间</label>
          <NDatePicker
            id="create-task-start-time"
            :value="startTimeValue"
            :is-date-disabled="isStartDateDisabled"
            class="field-input"
            format="yyyy-MM-dd HH:mm"
            time-picker-format="HH:mm"
            type="datetime"
            clearable
            value-format="timestamp"
            @update:value="handleStartTimeChange"
          />
          <p class="field-helper">选填，必须大于当前时间，精确到分钟</p>
          <p v-if="errors.startTime" class="field-error">{{ errors.startTime }}</p>
        </section>

        <section class="form-block">
          <p class="field-label">3. 筛选达人</p>
          <label class="field-item full-width search-row">
            <span>{{ getFilterLabel('searchKeyword') }}</span>
            <NInput
              v-model:value="form.searchKeyword"
              class="field-input"
              :placeholder="getFilterPlaceholder('searchKeyword')"
              type="text"
            />
          </label>

          <div class="creator-filter-panel">
            <div class="creator-filter-tabs-wrap">
              <span class="creator-filter-panel-title">{{ getFilterLabel('filterConditions') }}</span>
              <NTabs v-model:value="activeCreatorFilterTab" animated class="creator-filter-tabs" pane-class="creator-filter-tab-panel">
                <NTabPane v-for="item in CREATOR_FILTER_TAB_OPTIONS" :key="item.value" :name="item.value" :tab="item.label">
                  <template v-if="item.value === 'creator'">
                    <div class="form-grid three-col">
                      <div class="field-item">
                        <FilterFieldLabel :label="getFilterLabel('productCategory')" :tip-text="FILTER_TIPS.productCategory" />
                        <NSelect
                          v-model:value="form.creatorFilters.productCategorySelections"
                          :options="productCategoryOptions"
                          :placeholder="getFilterPlaceholder('selectDefault')"
                          class="field-input field-multi"
                          clearable
                          filterable
                          multiple
                        />
                      </div>
                      <div class="field-item">
                        <FilterFieldLabel :label="getFilterLabel('avgCommissionRate')" :tip-text="FILTER_TIPS.avgCommissionRate" />
                        <NSelect
                          v-model:value="form.creatorFilters.avgCommissionRate"
                          :options="avgCommissionRateOptions"
                          :placeholder="getFilterPlaceholder('selectDefault')"
                          class="field-input"
                        />
                      </div>
                      <div class="field-item">
                        <FilterFieldLabel :label="getFilterLabel('contentType')" :tip-text="FILTER_TIPS.contentType" />
                        <NSelect
                          v-model:value="form.creatorFilters.contentType"
                          :options="contentTypeOptions"
                          :placeholder="getFilterPlaceholder('selectDefault')"
                          class="field-input"
                        />
                      </div>
                      <div class="field-item">
                        <span>{{ getFilterLabel('creatorAgency') }}</span>
                        <NSelect
                          v-model:value="form.creatorFilters.creatorAgency"
                          :options="creatorAgencyOptions"
                          :placeholder="getFilterPlaceholder('selectDefault')"
                          class="field-input"
                        />
                      </div>
                    </div>

                    <div class="checkbox-row creator-filter-checkbox-row">
                      <!-- 后端未接好时可将 SHOW_SPOTLIGHT_CREATOR_FILTER 设为 false，仅隐藏展示，逻辑与文案已就绪 -->
                      <NCheckbox v-if="SHOW_SPOTLIGHT_CREATOR_FILTER" v-model:checked="form.creatorFilters.spotlightCreator">
                        <FilterFieldLabel
                          :label="getFilterLabel('spotlightCreator')"
                          :tip-text="FILTER_TIPS.spotlightCreator"
                        />
                      </NCheckbox>
                      <NCheckbox v-model:checked="form.creatorFilters.fastGrowing">
                        <FilterFieldLabel :label="getFilterLabel('fastGrowing')" :tip-text="FILTER_TIPS.fastGrowing" />
                      </NCheckbox>
                      <NCheckbox v-model:checked="form.creatorFilters.notInvitedInPast90Days">
                        <FilterFieldLabel
                          :label="getFilterLabel('notInvitedInPast90Days')"
                          :tip-text="FILTER_TIPS.notInvitedInPast90Days"
                        />
                      </NCheckbox>
                    </div>
                  </template>

                  <template v-else-if="item.value === 'followers'">
                    <div class="form-grid three-col">
                      <div class="field-item">
                        <span>{{ getFilterLabel('followerAge') }}</span>
                        <NSelect
                          v-model:value="form.followerFilters.followerAgeSelections"
                          :options="followerAgeOptions"
                          :placeholder="getFilterPlaceholder('selectDefault')"
                          class="field-input field-multi"
                          clearable
                          filterable
                          multiple
                        />
                      </div>
                      <div class="field-item">
                        <span>{{ getFilterLabel('followerGender') }}</span>
                        <NSelect
                          v-model:value="form.followerFilters.followerGender"
                          :options="followerGenderOptions"
                          :placeholder="getFilterPlaceholder('selectDefault')"
                          class="field-input"
                        />
                      </div>
                      <div class="field-item">
                        <span>{{ getFilterLabel('followerCountMin') }}</span>
                        <NInput v-model:value="form.followerFilters.followerCountMin" class="field-input" type="text" />
                        <div class="preset-option-row">
                          <NButton
                            v-for="option in followerCountPresetOptions"
                            :key="`follower-count-min-${String(option.value)}`"
                            size="tiny"
                            tertiary
                            type="primary"
                            @click="form.followerFilters.followerCountMin = String(option.value)"
                          >
                            {{ option.label }}
                          </NButton>
                        </div>
                      </div>
                      <div class="field-item">
                        <span>{{ getFilterLabel('followerCountMax') }}</span>
                        <NInput v-model:value="form.followerFilters.followerCountMax" class="field-input" type="text" />
                        <div class="preset-option-row">
                          <NButton
                            v-for="option in followerCountPresetOptions"
                            :key="`follower-count-max-${String(option.value)}`"
                            size="tiny"
                            tertiary
                            type="primary"
                            @click="form.followerFilters.followerCountMax = String(option.value)"
                          >
                            {{ option.label }}
                          </NButton>
                        </div>
                      </div>
                    </div>
                  </template>

                  <template v-else>
                    <div class="form-grid three-col">
                      <div class="field-item">
                        <FilterFieldLabel :label="getFilterLabel('gmv')" :tip-text="FILTER_TIPS.gmv" />
                        <NSelect
                          v-model:value="form.performanceFilters.gmvSelections"
                          :options="gmvOptions"
                          :placeholder="getFilterPlaceholder('selectDefault')"
                          class="field-input field-multi"
                          clearable
                          filterable
                          multiple
                        />
                      </div>
                      <div class="field-item">
                        <FilterFieldLabel :label="getFilterLabel('itemsSold')" :tip-text="FILTER_TIPS.itemsSold" />
                        <NSelect
                          v-model:value="form.performanceFilters.itemsSoldSelections"
                          :options="itemsSoldOptions"
                          :placeholder="getFilterPlaceholder('selectDefault')"
                          class="field-input field-multi"
                          clearable
                          filterable
                          multiple
                        />
                      </div>
                      <div class="field-item">
                        <span>{{ getFilterLabel('averageViewsPerVideoMin') }}</span>
                        <NInput v-model:value="form.performanceFilters.averageViewsPerVideoMin" class="field-input" type="text" />
                        <div class="preset-option-row">
                          <NButton
                            v-for="option in avgVideoViewsPresetOptions"
                            :key="`avg-video-views-${String(option.value)}`"
                            size="tiny"
                            tertiary
                            type="primary"
                            @click="form.performanceFilters.averageViewsPerVideoMin = String(option.value)"
                          >
                            {{ option.label }}
                          </NButton>
                        </div>
                      </div>
                      <div class="field-item">
                        <span>{{ getFilterLabel('averageViewersPerLiveMin') }}</span>
                        <NInput v-model:value="form.performanceFilters.averageViewersPerLiveMin" class="field-input" type="text" />
                        <div class="preset-option-row">
                          <NButton
                            v-for="option in avgLiveViewsPresetOptions"
                            :key="`avg-live-views-${String(option.value)}`"
                            size="tiny"
                            tertiary
                            type="primary"
                            @click="form.performanceFilters.averageViewersPerLiveMin = String(option.value)"
                          >
                            {{ option.label }}
                          </NButton>
                        </div>
                      </div>
                      <div class="field-item">
                        <FilterFieldLabel
                          :label="getFilterLabel('engagementRateMinPercent')"
                          :tip-text="FILTER_TIPS.engagementRateMinPercent"
                        />
                        <NInput v-model:value="form.performanceFilters.engagementRateMinPercent" class="field-input" type="text" />
                        <div class="preset-option-row">
                          <NButton
                            v-for="option in engagementRatePresetOptions"
                            :key="`engagement-rate-${String(option.value)}`"
                            size="tiny"
                            tertiary
                            type="primary"
                            @click="form.performanceFilters.engagementRateMinPercent = String(option.value)"
                          >
                            {{ option.label }}
                          </NButton>
                        </div>
                      </div>
                      <div class="field-item">
                        <FilterFieldLabel :label="getFilterLabel('estPostRate')" :tip-text="FILTER_TIPS.estPostRate" />
                        <NSelect
                          v-model:value="form.performanceFilters.estPostRate"
                          :options="estPostRateOptions"
                          :placeholder="getFilterPlaceholder('selectDefault')"
                          class="field-input"
                        />
                      </div>
                      <div class="field-item full-span">
                        <FilterFieldLabel
                          :label="getFilterLabel('brandCollaborations')"
                          :tip-text="FILTER_TIPS.brandCollaborations"
                        />
                        <NInput
                          v-model:value="form.performanceFilters.brandCollaborationInput"
                          class="field-input"
                          :placeholder="getFilterPlaceholder('brandCollaborations')"
                          type="text"
                        />
                      </div>
                    </div>

                    <!-- 暂未接入后端字段，先隐藏保留
                    <div class="checkbox-row">
                      <NCheckbox v-model:checked="form.performanceFilters.averageViewsPerVideoShoppableVideosOnly">
                        {{ avgVideoViewsToggleLabel }}
                      </NCheckbox>
                      <NCheckbox v-model:checked="form.performanceFilters.averageViewersPerLiveShoppableLiveOnly">
                        {{ avgLiveViewsToggleLabel }}
                      </NCheckbox>
                      <NCheckbox v-model:checked="form.performanceFilters.engagementRateShoppableVideosOnly">
                        {{ engagementRateToggleLabel }}
                      </NCheckbox>
                    </div>
                    -->
                  </template>
                </NTabPane>
              </NTabs>
            </div>
          </div>
        </section>

        <section class="form-block">
          <label class="field-label" for="create-task-sort">4. 达人排序</label>
          <NSelect id="create-task-sort" v-model:value="form.creatorSort" :options="sortOptions" class="field-input" />
          <p class="field-helper">默认选择官方默认值</p>
        </section>

        <section class="form-block" data-error-key="planCount">
          <label class="field-label" for="create-task-plan-count">5. 建联人数</label>
          <NInput
            id="create-task-plan-count"
            v-model:value="form.planCount"
            class="field-input"
            placeholder="请输入建联人数"
            type="text"
            inputmode="numeric"
          />
          <p class="field-helper">必填，当前权限下当前任务最多可联系人数 {{ maxPlanCount }}</p>
          <p v-if="errors.planCount" class="field-error">{{ errors.planCount }}</p>
        </section>

        <section class="form-block" data-error-key="outreachCreatorType">
          <label class="field-label" for="create-task-outreach-type">6. 建联达人</label>
          <NSelect id="create-task-outreach-type" v-model:value="form.outreachCreatorType" :options="OUTREACH_CREATOR_OPTIONS" class="field-input" />
          <p v-if="errors.outreachCreatorType" class="field-error">{{ errors.outreachCreatorType }}</p>
        </section>

        <section class="form-block">
          <p class="field-label">7. 消息模板</p>
          <p class="field-helper">{{ messageTip }}</p>

          <div v-if="isAllCreatorMode" class="message-tab-row">
            <NTabs v-model:value="activeMessageTab" animated type="line" class="message-tabs">
              <NTabPane v-for="item in MESSAGE_TAB_OPTIONS" :key="item.value" :name="item.value" :tab="item.label" />
            </NTabs>
          </div>

          <div v-show="activeMessageTab === 'first'" class="message-panel" data-error-key="firstMessageContent">
            <label class="field-item full-width">
              <span>首次消息</span>
              <NInput
                v-model:value="form.firstMessage.content"
                :autosize="{ minRows: 4, maxRows: 10 }"
                class="field-input field-textarea"
                maxlength="2000"
                placeholder="请输入首次消息模板"
                type="textarea"
              />
            </label>
            <div class="field-helper">
              <span>消息长度需参考 TikTok 约束，最多 2000 字</span>
              <span>{{ form.firstMessage.content.length }}/2000</span>
            </div>
            <p v-if="errors.firstMessageContent" class="field-error">{{ errors.firstMessageContent }}</p>

            <NCheckbox v-model:checked="form.firstMessage.enableProductMessage" class="checkbox-single" @update:checked="handleProductMessageToggle('first')">
              商品消息
            </NCheckbox>
            <div v-if="form.firstMessage.enableProductMessage" class="product-message-wrap" data-error-key="firstProductIds">
              <div class="id-tags">
                <NTag
                  v-for="item in form.firstMessage.productIds"
                  :key="item"
                  closable
                  class="id-tag"
                  @close="removeMessageProductId('first', item)"
                >
                  {{ item }}
                </NTag>
              </div>
              <NInput
                v-model:value="form.firstMessage.productInput"
                class="field-input"
                placeholder="输入商品ID后按回车，最多4个"
                type="text"
                @blur="flushMessageProductInput('first')"
                @keydown="handleProductInputKeydown($event, 'first')"
              />
              <p v-if="errors.firstProductIds" class="field-error">{{ errors.firstProductIds }}</p>
            </div>
          </div>

          <div v-if="isAllCreatorMode" v-show="activeMessageTab === 'reply'" class="message-panel" data-error-key="replyMessageContent">
            <label class="field-item full-width">
              <span>回复达人消息</span>
              <NInput
                v-model:value="form.replyMessage.content"
                :autosize="{ minRows: 4, maxRows: 10 }"
                class="field-input field-textarea"
                maxlength="2000"
                placeholder="请输入回复达人消息模板"
                type="textarea"
              />
            </label>
            <div class="field-helper">
              <span>消息长度需参考 TikTok 约束，最多 2000 字</span>
              <span>{{ form.replyMessage.content.length }}/2000</span>
            </div>
            <p v-if="errors.replyMessageContent" class="field-error">{{ errors.replyMessageContent }}</p>

            <NCheckbox v-model:checked="form.replyMessage.enableProductMessage" class="checkbox-single" @update:checked="handleProductMessageToggle('reply')">
              商品消息
            </NCheckbox>
            <div v-if="form.replyMessage.enableProductMessage" class="product-message-wrap" data-error-key="replyProductIds">
              <div class="id-tags">
                <NTag
                  v-for="item in form.replyMessage.productIds"
                  :key="item"
                  closable
                  class="id-tag"
                  @close="removeMessageProductId('reply', item)"
                >
                  {{ item }}
                </NTag>
              </div>
              <NInput
                v-model:value="form.replyMessage.productInput"
                class="field-input"
                placeholder="输入商品ID后按回车，最多4个"
                type="text"
                @blur="flushMessageProductInput('reply')"
                @keydown="handleProductInputKeydown($event, 'reply')"
              />
              <p v-if="errors.replyProductIds" class="field-error">{{ errors.replyProductIds }}</p>
            </div>
          </div>

          <p class="description-text">
            说明：发送首次建联消息，如达人已回复，则发送回复达人消息。仅当建联所有达人时，才出现回复达人消息设置。
          </p>
        </section>
      </div>

      <footer class="modal-footer">
        <NButton :disabled="saving" @click="resetForm">重置</NButton>
        <NButton type="primary" :loading="saving" @click="handleSubmit">{{ saving ? '保存中...' : '确定' }}</NButton>
      </footer>
    </NCard>
  </NModal>
</template>

<style scoped>
.modal-card {
  width: 720px;
  max-width: calc(100vw - 32px);
  height: min(860px, calc(100vh - 40px));
  max-height: calc(100vh - 40px);
  border-radius: 12px;
  box-shadow: 0 18px 48px rgba(11, 27, 52, 0.35);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-card:deep(.n-card__content) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #ecf1f7;
  background: #fff;
}

.modal-header h2 {
  margin: 0;
  font-size: 18px;
  color: #1f2d3d;
}

.close-btn {
  color: #6b7b90;
  font-size: 20px;
  --n-color-focus: transparent !important;
}

.close-btn:deep(.n-button__content) {
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-symbol {
  display: block;
  line-height: 1;
  transform: translateY(-1px);
}

.modal-body {
  flex: 1;
  overflow: auto;
  min-height: 0;
  padding: 16px 18px;
  background: #f4f7fb;
}

.submit-error {
  margin: 0 0 10px;
  border: 1px solid #ffc5c5;
  background: #fff3f3;
  color: #b42318;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
}

.form-block {
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #fff;
  padding: 14px;
  margin-bottom: 12px;
}

.field-label {
  display: block;
  font-size: 14px;
  font-weight: 700;
  color: #1f2d3d;
  margin-bottom: 10px;
}

.field-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-item > span {
  font-size: 13px;
  color: #3c4a5b;
}

.field-input {
  width: 100%;
  color: #1f2d3d;
  font-size: 14px;
}

.field-input:deep(.n-input-wrapper),
.field-input:deep(.n-base-selection),
.field-input:deep(.n-date-picker) .n-input-wrapper {
  border-radius: 8px;
  font-size: 14px;
}

.field-input:deep(.n-input__input-el),
.field-input:deep(textarea) {
  color: #1f2d3d;
  font-size: 14px;
}

.field-input:deep(.n-base-selection) {
  min-height: 36px;
}

.field-multi {
  min-height: 36px;
}

.field-multi:deep(.n-base-selection) {
  min-height: 36px;
  padding: 2px 8px;
}

.field-multi:deep(.n-base-selection-tag) {
  background: #eef5ff;
}

.field-multi:deep(.n-tag) {
  --n-border: 1px solid #cce2ff !important;
  --n-color: #eef5ff !important;
  --n-text-color: #1f63d8 !important;
}

.field-textarea {
  min-height: 112px;
}

.field-textarea:deep(textarea) {
  min-height: 112px;
  resize: vertical;
}

.form-grid {
  display: grid;
  gap: 12px;
  margin-bottom: 10px;
}

.three-col {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.two-col {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.full-width {
  width: 100%;
}

.full-span {
  grid-column: 1 / -1;
}

.search-row {
  margin-bottom: 14px;
}

.creator-filter-panel {
  border: 1px solid #ecf1f7;
  border-radius: 12px;
  background: #fcfdff;
  padding: 14px;
}

.creator-filter-tabs-wrap {
  position: relative;
}

.creator-filter-panel-title {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 1;
  font-size: 14px;
  font-weight: 600;
  color: #3c4a5b;
  white-space: nowrap;
  line-height: 32px;
}

.creator-filter-tabs {
  width: 100%;
}

.creator-filter-tabs:deep(.n-tabs-nav) {
  margin-bottom: 12px;
  padding-left: 86px;
}

.creator-filter-tabs:deep(.n-tabs-nav-scroll-wrapper) {
  display: flex;
}

.creator-filter-tabs:deep(.n-tabs-nav-scroll-content) {
  display: inline-flex;
  align-items: center;
}

.creator-filter-tabs:deep(.n-tabs-tab-wrapper) {
  margin-right: 6px;
}

.creator-filter-tabs:deep(.n-tabs-tab) {
  display: inline-flex;
  align-items: center;
  min-width: 132px;
  justify-content: center;
  height: 34px;
  box-sizing: border-box;
  padding: 0 20px;
  border-radius: 10px;
  background: #f3f5f7;
  color: #1f2d3d;
  overflow: hidden;
  transition:
    background-color 0.2s ease,
    color 0.2s ease;
}

.creator-filter-tabs:deep(.n-tabs-tab__label) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  line-height: 1;
}

.creator-filter-tabs:deep(.n-tabs-tab--active) {
  background: #dff7fb;
  color: #0f67ff;
}

.creator-filter-tabs:deep(.n-tabs-bar) {
  display: none;
}

.creator-filter-tabs:deep(.n-tab-pane) {
  padding-top: 0;
}

.creator-filter-tab-panel {
  min-height: 120px;
}

.creator-filter-checkbox-row {
  margin-bottom: 0;
}

.creator-filter-checkbox-row :deep(.n-checkbox__label) {
  display: inline-flex;
  align-items: center;
}

.checkbox-row {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin: 8px 0 12px;
  font-size: 13px;
  color: #3c4a5b;
}

.preset-option-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 2px;
}

.checkbox-single {
  display: inline-flex;
  margin: 10px 0 6px;
  color: #344355;
  font-size: 13px;
}

.field-helper {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
  color: #5b6d83;
  font-size: 12px;
}

.field-error {
  margin: 6px 0 0;
  color: #d92d20;
  font-size: 12px;
}

.message-tab-row {
  display: flex;
  margin: 8px 0;
}

.message-tabs {
  width: fit-content;
}

.message-tabs:deep(.n-tabs-pane-wrapper) {
  display: none;
}

.message-panel {
  border: 1px solid #dbe3ef;
  border-radius: 8px;
  padding: 12px;
  margin-top: 8px;
  background: #f8fbff;
}

.product-message-wrap {
  border: 1px dashed #cce2ff;
  border-radius: 8px;
  padding: 10px;
  background: #eef5ff;
}

.id-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.id-tag {
  --n-border: 1px solid #cce2ff !important;
  --n-color: #eef5ff !important;
  --n-text-color: #1f63d8 !important;
  --n-close-color: #1f63d8 !important;
  --n-close-color-hover: #0f67ff !important;
}

.description-text {
  margin: 10px 0 0;
  font-size: 12px;
  color: #5b6d83;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid #ecf1f7;
  padding: 12px 18px;
  background: #fff;
}

.modal-footer :deep(.n-button) {
  min-width: 88px;
  border-radius: 8px;
}

.modal-footer :deep(.n-button__content) {
  font-size: 14px;
}

@media (max-width: 900px) {
  .three-col,
  .two-col {
    grid-template-columns: minmax(0, 1fr);
  }

  .creator-filter-tabs-wrap {
    position: static;
  }

  .creator-filter-panel-title {
    position: static;
    display: block;
    margin-bottom: 8px;
    line-height: 1.4;
  }

  .creator-filter-tabs:deep(.n-tabs-nav) {
    padding-left: 0;
  }

  .modal-header h2 {
    font-size: 16px;
  }
}
</style>
