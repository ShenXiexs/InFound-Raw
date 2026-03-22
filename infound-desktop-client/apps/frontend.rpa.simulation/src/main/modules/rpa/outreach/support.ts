import type {
  AvgCommissionRateOption,
  ContentTypeOption,
  CreatorAgencyOption,
  CreatorFilterConfig,
  FollowerAgeOption,
  FollowerFilterConfig,
  FollowerGenderOption,
  OutreachFilterConfig,
  OutreachFilterConfigInput,
  PerformanceEstPostRateOption,
  PerformanceFilterConfig,
  PerformanceGmvOption,
  PerformanceItemsSoldOption
} from '@common/types/rpa-outreach'
import type { BrowserAction } from '../task-dsl/browser-actions'

// This file is the frontend DSL implementation for MX outreach filters, aligned with
// infound-data-collection/apps/portal_tiktok_shop_collection/scripts/outreach_filter_base.py
// and outreach_filter_mx.py.
interface CreatorProductCategoryOption {
  label: string
  value: string
}

type ScriptRecord = Record<string, unknown>

const CREATOR_PRODUCT_CATEGORY_OPTIONS: CreatorProductCategoryOption[] = [
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

const CREATOR_PRODUCT_CATEGORY_VALUE_SET = new Set(CREATOR_PRODUCT_CATEGORY_OPTIONS.map((item) => item.value))
const CREATOR_PRODUCT_CATEGORY_LABEL_TO_VALUE = new Map(
  CREATOR_PRODUCT_CATEGORY_OPTIONS.map((item) => [item.label.toLowerCase(), item.value] as const)
)

const AVG_COMMISSION_RATE_OPTIONS: AvgCommissionRateOption[] = [
  'All',
  'Less than 20%',
  'Less than 15%',
  'Less than 10%',
  'Less than 5%'
]
const CONTENT_TYPE_OPTIONS: ContentTypeOption[] = ['All', 'Video', 'LIVE']
const CREATOR_AGENCY_OPTIONS: CreatorAgencyOption[] = ['All', 'Managed by Agency', 'Independent creators']
const FOLLOWER_AGE_OPTIONS: FollowerAgeOption[] = ['18 - 24', '25 - 34', '35 - 44', '45 - 54', '55+']
const FOLLOWER_GENDER_OPTIONS: FollowerGenderOption[] = ['All', 'Female', 'Male']
const PERFORMANCE_GMV_OPTIONS: PerformanceGmvOption[] = ['MX$0-MX$100', 'MX$100-MX$1K', 'MX$1K-MX$10K', 'MX$10K+']
const PERFORMANCE_ITEMS_SOLD_OPTIONS: PerformanceItemsSoldOption[] = ['0-10', '10-100', '100-1K', '1K+']
const PERFORMANCE_EST_POST_RATE_OPTIONS: PerformanceEstPostRateOption[] = ['All', 'OK', 'Good', 'Better']

const MODULE_BUTTON_SELECTOR = 'button[data-tid="m4b_button"] span'
const FILTER_TITLE_SELECTOR = 'button[data-tid="m4b_button"] .arco-typography'
const PRODUCT_CATEGORY_PANEL_SELECTOR = 'ul.arco-cascader-list.arco-cascader-list-multiple'
const SINGLE_SELECT_OPTION_SELECTOR = 'li.arco-select-option'
const MULTI_SELECT_OPTION_SELECTOR = 'span.arco-select-option.m4b-select-option'
const MULTI_SELECT_POPUP_SELECTOR = 'div.arco-select-popup.arco-select-popup-multiple'
const FOLLOWER_COUNT_RANGE_SELECTOR = 'div[data-e2e="ec40fffd-2fcf-30d5"]'
const FOLLOWER_COUNT_MIN_INPUT_SELECTOR = `${FOLLOWER_COUNT_RANGE_SELECTOR} input[data-e2e="d9c26458-94d3-e920"]`
const FOLLOWER_COUNT_MAX_INPUT_SELECTOR = `${FOLLOWER_COUNT_RANGE_SELECTOR} input[data-e2e="b7512111-8b2f-a07b"]`
const POPUP_THRESHOLD_INPUT_SELECTOR = 'input[data-tid="m4b_input"][data-e2e="7f6a7b3f-260b-00c0"]'
const POPUP_CHECKBOX_LABEL_SELECTOR = 'label[data-tid="m4b_checkbox"]'
const POPUP_SCROLL_CONTAINER_SELECTOR = '.arco-select-popup-inner'
const OUTREACH_FILTER_DISMISS_TEXT = 'Find creators'
const OUTREACH_FILTER_DISMISS_SELECTOR = 'button span, h1, h2, h3, p, span, div'
const OUTREACH_STEP_RETRY_COUNT = 3
const OUTREACH_STEP_ERROR_POLICY = 'continue' as const
const SEARCH_INPUT_SELECTOR = 'input[data-tid="m4b_input_search"]'
const OUTREACH_SCROLL_CONTAINER_SELECTOR = '#modern_sub_app_container_connection'

export const CREATOR_MARKETPLACE_CAPTURE_KEY = 'creator_marketplace_results'
const CREATOR_MARKETPLACE_FIND_URL_KEYWORD = '/api/v1/oec/affiliate/creator/marketplace/find'
export const CREATOR_MARKETPLACE_DATA_KEY = 'creator_marketplace_creators'
export const CREATOR_MARKETPLACE_SUMMARY_KEY = 'creator_marketplace_summary'
export const CREATOR_MARKETPLACE_FILE_PATH_KEY = 'creator_marketplace_file_path'
export const CREATOR_MARKETPLACE_EXCEL_FILE_PATH_KEY = 'creator_marketplace_excel_file_path'
export const CREATOR_MARKETPLACE_RAW_DATA_KEY = 'creator_marketplace_raw_creators'
export const CREATOR_MARKETPLACE_RAW_FILE_PATH_KEY = 'creator_marketplace_raw_file_path'
export const CREATOR_MARKETPLACE_RAW_DIRECTORY_PATH_KEY = 'creator_marketplace_raw_directory_path'

const MODULE_BUTTON_FALLBACK_TEXTS: Record<string, string[]> = {
  Followers: ['Follower']
}

const createDefaultOutreachFilterConfig = (): OutreachFilterConfig => ({
  creatorFilters: {
    productCategorySelections: ['Home Supplies'],
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
    brandCollaborationSelections: []
  },
  searchKeyword: ''
})

export const createDemoOutreachFilterConfig = (): OutreachFilterConfigInput => ({
  creatorFilters: {
    productCategorySelections: ['Home Supplies', 'Beauty & Personal Care', 'Phones & Electronics'],
    avgCommissionRate: 'Less than 20%',
    contentType: 'Video',
    creatorAgency: 'Independent creators',
    spotlightCreator: true,
    fastGrowing: true,
    notInvitedInPast90Days: true
  },
  followerFilters: {
    followerAgeSelections: ['18 - 24', '25 - 34'],
    followerGender: 'Female',
    followerCountMin: '10000',
    followerCountMax: '200000'
  },
  performanceFilters: {
    gmvSelections: ['MX$100-MX$1K', 'MX$1K-MX$10K'],
    itemsSoldSelections: ['10-100', '100-1K'],
    averageViewsPerVideoMin: '1000',
    averageViewsPerVideoShoppableVideosOnly: true,
    averageViewersPerLiveMin: '300',
    averageViewersPerLiveShoppableLiveOnly: true,
    engagementRateMinPercent: '5',
    engagementRateShoppableVideosOnly: true,
    estPostRate: 'Good',
    brandCollaborationSelections: ["L'OREAL PROFESSIONNEL", 'Maybelline New York', 'NYX Professional Makeup']
  },
  searchKeyword: 'lipstick'
})

export const mergeOutreachFilterConfig = (input?: OutreachFilterConfigInput): OutreachFilterConfig => {
  const defaults = createDefaultOutreachFilterConfig()
  return {
    creatorFilters: {
      ...defaults.creatorFilters,
      ...(input?.creatorFilters ?? {})
    },
    followerFilters: {
      ...defaults.followerFilters,
      ...(input?.followerFilters ?? {})
    },
    performanceFilters: {
      ...defaults.performanceFilters,
      ...(input?.performanceFilters ?? {})
    },
    searchKeyword: input?.searchKeyword ?? defaults.searchKeyword
  }
}

export const isOutreachFilterConfigInput = (value: unknown): value is OutreachFilterConfigInput => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const candidate = value as Record<string, unknown>
  return (
    'creatorFilters' in candidate ||
    'followerFilters' in candidate ||
    'performanceFilters' in candidate ||
    'searchKeyword' in candidate
  )
}

const normalizeCreatorProductCategoryValues = (selections: string[]): string[] => {
  const normalizedValues: string[] = []
  const seen = new Set<string>()

  for (const rawSelection of selections) {
    const token = String(rawSelection || '').trim()
    if (!token) continue

    let value = ''
    if (CREATOR_PRODUCT_CATEGORY_VALUE_SET.has(token)) {
      value = token
    } else {
      const matched = CREATOR_PRODUCT_CATEGORY_LABEL_TO_VALUE.get(token.toLowerCase())
      if (matched) {
        value = matched
      }
    }

    if (!value) {
      throw new Error(`未知 Product category 选项: ${token}`)
    }

    if (!seen.has(value)) {
      seen.add(value)
      normalizedValues.push(value)
    }
  }

  return normalizedValues
}

const normalizeSingleSelectOption = <T extends string>(selection: string, options: readonly T[], optionName: string): T => {
  const token = String(selection || '').trim()
  const matched = options.find((item) => item.toLowerCase() === token.toLowerCase())
  if (!matched) {
    throw new Error(`未知 ${optionName} 选项: ${selection}`)
  }
  return matched
}

const normalizeMultiSelectOptions = <T extends string>(
  selections: string[],
  options: readonly T[],
  optionName: string
): T[] => {
  const seen = new Set<string>()
  const normalized: T[] = []

  for (const rawSelection of selections) {
    const token = String(rawSelection || '').trim()
    if (!token) continue

    const matched = options.find((item) => item.toLowerCase() === token.toLowerCase())
    if (!matched) {
      throw new Error(`未知 ${optionName} 选项: ${rawSelection}`)
    }

    if (!seen.has(matched)) {
      seen.add(matched)
      normalized.push(matched)
    }
  }

  return normalized
}

const normalizeFreeformSelections = (selections: string[]): string[] => {
  const normalized: string[] = []
  const seen = new Set<string>()

  for (const rawSelection of selections) {
    const token = String(rawSelection || '').trim()
    if (!token || seen.has(token.toLowerCase())) continue
    seen.add(token.toLowerCase())
    normalized.push(token)
  }

  return normalized
}

const asRecord = (value: unknown): ScriptRecord | null =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as ScriptRecord) : null

const asArray = (value: unknown): unknown[] => (Array.isArray(value) ? value : [])

const readScriptValue = (record: ScriptRecord | null, ...keys: string[]): unknown => {
  if (!record) {
    return undefined
  }
  for (const key of keys) {
    if (key in record) {
      return record[key]
    }
  }
  return undefined
}

const readScriptText = (record: ScriptRecord | null, ...keys: string[]): string => {
  const value = readScriptValue(record, ...keys)
  return String(value ?? '').trim()
}

const readScriptTextList = (record: ScriptRecord | null, ...keys: string[]): string[] => {
  const value = readScriptValue(record, ...keys)
  return asArray(value)
    .map((item) => String(item ?? '').trim())
    .filter(Boolean)
}

const buildOutreachDismissPayload = (dismissText = OUTREACH_FILTER_DISMISS_TEXT) => ({
  closeText: dismissText,
  closeSelector: OUTREACH_FILTER_DISMISS_SELECTOR
})

const buildModuleButtonAction = (
  moduleTitle: string,
  postClickWaitMs = 350,
  selector = MODULE_BUTTON_SELECTOR,
  fallbackTexts?: string[]
): BrowserAction => ({
  id: `切换到${moduleTitle}筛选模块`,
  actionType: 'clickByText',
  payload: {
    text: moduleTitle,
    fallbackTexts: fallbackTexts ?? MODULE_BUTTON_FALLBACK_TEXTS[moduleTitle] ?? [],
    selector,
    exact: true,
    caseSensitive: false,
    timeoutMs: 10000,
    intervalMs: 250,
    postClickWaitMs
  },
  options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
  onError: OUTREACH_STEP_ERROR_POLICY
})

const resolveThresholdCheckboxLabel = (
  filterKey: string,
  filterSpec: ScriptRecord | null
): string | undefined => {
  const snapshot = asRecord(readScriptValue(filterSpec, 'snapshot'))
  const checkboxLabels = asArray(readScriptValue(snapshot, 'checkboxLabels', 'checkbox_labels'))
    .map((item) => readScriptText(asRecord(item), 'label'))
    .filter(Boolean)

  const matcher =
    filterKey === 'averageViewersPerLiveMin'
      ? (label: string) => label.toLowerCase().includes('shoppable live')
      : (label: string) => label.toLowerCase().includes('shoppable videos')

  return checkboxLabels.find(matcher)
}

const buildSearchKeywordStepsFromScript = (
  keyword: string,
  binding: ScriptRecord | null,
  dismissText: string
): BrowserAction[] => {
  const normalizedKeyword = String(keyword || '').trim()
  const selector = readScriptText(binding, 'selector') || SEARCH_INPUT_SELECTOR
  const effectiveDismissText =
    readScriptText(binding, 'dismissText', 'dismiss_text') || dismissText

  return [
    {
      actionType: 'startJsonResponseCapture',
      payload: {
        captureKey: CREATOR_MARKETPLACE_CAPTURE_KEY,
        urlIncludes: CREATOR_MARKETPLACE_FIND_URL_KEYWORD,
        method: 'POST',
        reset: true
      },
      options: { retryCount: 1 },
      onError: 'abort'
    },
    {
      actionType: 'fillSelector',
      payload: {
        selector,
        value: normalizedKeyword,
        waitForState: 'visible',
        timeoutMs: 10000,
        intervalMs: 250,
        clearBeforeFill: true,
        postFillWaitMs: 120
      },
      options: { retryCount: 2 },
      onError: 'abort'
    },
    {
      actionType: 'clickByText',
      payload: {
        text: effectiveDismissText,
        selector: OUTREACH_FILTER_DISMISS_SELECTOR,
        exact: true,
        caseSensitive: false,
        timeoutMs: 10000,
        intervalMs: 250,
        postClickWaitMs: 120
      },
      options: { retryCount: 2 },
      onError: 'abort'
    },
    {
      actionType: 'clickSelector',
      payload: {
        selector,
        waitForState: 'visible',
        timeoutMs: 5000,
        intervalMs: 250,
        postClickWaitMs: 80
      },
      options: { retryCount: 2 },
      onError: 'abort'
    },
    {
      actionType: 'pressKey',
      payload: {
        key: 'Enter',
        postKeyWaitMs: 3000
      },
      options: { retryCount: 1 },
      onError: 'abort'
    }
  ]
}

const buildScriptDrivenFilterSteps = (
  filters: OutreachFilterConfig,
  script: ScriptRecord
): BrowserAction[] | null => {
  const source = asRecord(readScriptValue(script, 'source'))
  const modules = asArray(readScriptValue(script, 'modules'))
  if (!modules.length) {
    return null
  }

  const dismissText =
    readScriptText(source, 'pageReadyText', 'page_ready_text') || OUTREACH_FILTER_DISMISS_TEXT
  const moduleButtonSelector =
    readScriptText(source, 'moduleButtonSelector', 'module_button_selector') ||
    MODULE_BUTTON_SELECTOR
  const filterTitleSelector =
    readScriptText(source, 'filterTitleSelector', 'filter_title_selector') ||
    FILTER_TITLE_SELECTOR

  const allSteps: BrowserAction[] = []

  for (const moduleValue of modules) {
    const moduleSpec = asRecord(moduleValue)
    if (!moduleSpec) {
      continue
    }
    const moduleButton = asRecord(readScriptValue(moduleSpec, 'moduleButton', 'module_button'))
    const moduleTitle =
      readScriptText(moduleSpec, 'moduleTitle', 'module_title') ||
      readScriptText(moduleButton, 'text')
    if (!moduleTitle) {
      continue
    }

    const moduleFilterSteps: BrowserAction[] = []
    for (const filterValue of asArray(readScriptValue(moduleSpec, 'filters'))) {
      const filterSpec = asRecord(filterValue)
      const binding = asRecord(readScriptValue(filterSpec, 'dslBinding', 'dsl_binding'))
      const filterKey =
        readScriptText(binding, 'filterKey', 'filter_key') ||
        readScriptText(filterSpec, 'filterKey', 'filter_key')
      if (!filterKey) {
        continue
      }

      const triggerTexts = readScriptTextList(binding, 'triggerTexts', 'trigger_texts')
      const triggerText =
        triggerTexts[0] ||
        readScriptText(binding, 'filterTitle', 'filter_title') ||
        readScriptText(filterSpec, 'filterTitle', 'filter_title')
      const triggerFallbackTexts = triggerTexts.slice(1)
      const triggerSelector =
        readScriptText(binding, 'triggerSelector', 'trigger_selector') || filterTitleSelector
      const actionType = readScriptText(binding, 'actionType', 'action_type')
      const waitSelector = readScriptText(binding, 'waitSelector', 'wait_selector')
      const optionSelector = readScriptText(binding, 'optionSelector', 'option_selector')
      const panelSelector = readScriptText(binding, 'panelSelector', 'panel_selector')
      const scrollContainerSelector =
        readScriptText(binding, 'scrollContainerSelector', 'scroll_container_selector') ||
        panelSelector

      if (filterKey === 'productCategorySelections') {
        const values = normalizeCreatorProductCategoryValues(filters.creatorFilters.productCategorySelections)
        if (values.length && actionType === 'selectCascaderOptionsByValue') {
          moduleFilterSteps.push({
            actionType: 'selectCascaderOptionsByValue',
            payload: {
              triggerText,
              triggerFallbackTexts,
              triggerSelector,
              panelSelector: panelSelector || PRODUCT_CATEGORY_PANEL_SELECTOR,
              values,
              inputSelector: 'input[type="checkbox"]',
              scrollContainerSelector: scrollContainerSelector || PRODUCT_CATEGORY_PANEL_SELECTOR,
              scrollStepPx: 320,
              maxScrollAttempts: 20,
              timeoutMs: 10000,
              intervalMs: 250,
              triggerPostClickWaitMs: 300,
              optionPostClickWaitMs: 180,
              closeAfterSelect: true
            },
            options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
            onError: OUTREACH_STEP_ERROR_POLICY
          })
        }
        continue
      }

      if (filterKey === 'avgCommissionRate') {
        const optionText = normalizeSingleSelectOption(
          filters.creatorFilters.avgCommissionRate,
          AVG_COMMISSION_RATE_OPTIONS,
          'Avg. commission rate'
        )
        if (optionText !== 'All' && actionType === 'selectDropdownSingle') {
          moduleFilterSteps.push({
            actionType: 'selectDropdownSingle',
            payload: {
              triggerText,
              triggerFallbackTexts,
              triggerSelector,
              optionText,
              optionSelector: optionSelector || SINGLE_SELECT_OPTION_SELECTOR,
              waitSelector: waitSelector || SINGLE_SELECT_OPTION_SELECTOR,
              waitState: 'visible',
              exact: true,
              caseSensitive: false,
              timeoutMs: 10000,
              intervalMs: 250,
              triggerPostClickWaitMs: 250,
              optionPostClickWaitMs: 160,
              closeAfterSelect: true,
              ...buildOutreachDismissPayload(dismissText)
            },
            options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
            onError: OUTREACH_STEP_ERROR_POLICY
          })
        }
        continue
      }

      if (filterKey === 'contentType') {
        const optionText = normalizeSingleSelectOption(
          filters.creatorFilters.contentType,
          CONTENT_TYPE_OPTIONS,
          'Content type'
        )
        if (optionText !== 'All' && actionType === 'selectDropdownSingle') {
          moduleFilterSteps.push({
            actionType: 'selectDropdownSingle',
            payload: {
              triggerText,
              triggerFallbackTexts,
              triggerSelector,
              optionText,
              optionSelector: optionSelector || SINGLE_SELECT_OPTION_SELECTOR,
              waitSelector: waitSelector || SINGLE_SELECT_OPTION_SELECTOR,
              waitState: 'visible',
              exact: true,
              caseSensitive: false,
              timeoutMs: 10000,
              intervalMs: 250,
              triggerPostClickWaitMs: 250,
              optionPostClickWaitMs: 160,
              closeAfterSelect: true,
              ...buildOutreachDismissPayload(dismissText)
            },
            options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
            onError: OUTREACH_STEP_ERROR_POLICY
          })
        }
        continue
      }

      if (filterKey === 'creatorAgency') {
        const optionText = normalizeSingleSelectOption(
          filters.creatorFilters.creatorAgency,
          CREATOR_AGENCY_OPTIONS,
          'Creator agency'
        )
        if (optionText !== 'All' && actionType === 'selectDropdownSingle') {
          moduleFilterSteps.push({
            actionType: 'selectDropdownSingle',
            payload: {
              triggerText,
              triggerFallbackTexts,
              triggerSelector,
              optionText,
              optionSelector: optionSelector || SINGLE_SELECT_OPTION_SELECTOR,
              waitSelector: waitSelector || SINGLE_SELECT_OPTION_SELECTOR,
              waitState: 'visible',
              exact: true,
              caseSensitive: false,
              timeoutMs: 10000,
              intervalMs: 250,
              triggerPostClickWaitMs: 250,
              optionPostClickWaitMs: 160,
              closeAfterSelect: true,
              ...buildOutreachDismissPayload(dismissText)
            },
            options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
            onError: OUTREACH_STEP_ERROR_POLICY
          })
        }
        continue
      }

      if (
        (filterKey === 'spotlightCreator' && filters.creatorFilters.spotlightCreator) ||
        (filterKey === 'fastGrowing' && filters.creatorFilters.fastGrowing) ||
        (filterKey === 'notInvitedInPast90Days' &&
          filters.creatorFilters.notInvitedInPast90Days)
      ) {
        if (actionType === 'setCheckbox') {
          moduleFilterSteps.push({
            actionType: 'setCheckbox',
            payload: {
              selector: triggerSelector,
              checked: true,
              timeoutMs: 10000,
              intervalMs: 250,
              scrollContainerSelector: OUTREACH_SCROLL_CONTAINER_SELECTOR,
              scrollStepPx: 420,
              maxScrollAttempts: 20,
              postClickWaitMs: 150
            },
            options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
            onError: OUTREACH_STEP_ERROR_POLICY
          })
        }
        continue
      }

      if (filterKey === 'followerAgeSelections') {
        const optionTexts = normalizeMultiSelectOptions(
          filters.followerFilters.followerAgeSelections,
          FOLLOWER_AGE_OPTIONS,
          'Follower age'
        )
        if (optionTexts.length && actionType === 'selectDropdownMultiple') {
          moduleFilterSteps.push({
            actionType: 'selectDropdownMultiple',
            payload: {
              triggerText,
              triggerFallbackTexts,
              triggerSelector,
              optionTexts,
              optionSelector: optionSelector || MULTI_SELECT_OPTION_SELECTOR,
              waitSelector: waitSelector || MULTI_SELECT_POPUP_SELECTOR,
              waitState: 'visible',
              exact: true,
              caseSensitive: false,
              scrollContainerSelector: scrollContainerSelector || POPUP_SCROLL_CONTAINER_SELECTOR,
              timeoutMs: 10000,
              intervalMs: 250,
              triggerPostClickWaitMs: 300,
              optionPostClickWaitMs: 180,
              closeAfterSelect: true,
              ...buildOutreachDismissPayload(dismissText)
            },
            options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
            onError: OUTREACH_STEP_ERROR_POLICY
          })
        }
        continue
      }

      if (filterKey === 'followerGender') {
        const optionText = normalizeSingleSelectOption(
          filters.followerFilters.followerGender,
          FOLLOWER_GENDER_OPTIONS,
          'Follower gender'
        )
        if (optionText !== 'All' && actionType === 'selectDropdownSingle') {
          moduleFilterSteps.push({
            actionType: 'selectDropdownSingle',
            payload: {
              triggerText,
              triggerFallbackTexts,
              triggerSelector,
              optionText,
              optionSelector: optionSelector || SINGLE_SELECT_OPTION_SELECTOR,
              waitSelector: waitSelector || SINGLE_SELECT_OPTION_SELECTOR,
              waitState: 'visible',
              exact: true,
              caseSensitive: false,
              timeoutMs: 10000,
              intervalMs: 250,
              triggerPostClickWaitMs: 250,
              optionPostClickWaitMs: 160,
              closeAfterSelect: true,
              ...buildOutreachDismissPayload(dismissText)
            },
            options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
            onError: OUTREACH_STEP_ERROR_POLICY
          })
        }
        continue
      }

      if (filterKey === 'followerCountRange') {
        const hasRangeOverride =
          String(filters.followerFilters.followerCountMin).trim() !== '0' ||
          String(filters.followerFilters.followerCountMax).trim() !== '10,000,000+'
        if (hasRangeOverride && actionType === 'fillDropdownRange') {
          moduleFilterSteps.push({
            actionType: 'fillDropdownRange',
            payload: {
              triggerText,
              triggerFallbackTexts,
              triggerSelector,
              triggerExact: false,
              waitSelector: waitSelector || FOLLOWER_COUNT_RANGE_SELECTOR,
              minSelector:
                readScriptText(binding, 'minSelector', 'min_selector') ||
                FOLLOWER_COUNT_MIN_INPUT_SELECTOR,
              minValue: String(filters.followerFilters.followerCountMin),
              maxSelector:
                readScriptText(binding, 'maxSelector', 'max_selector') ||
                FOLLOWER_COUNT_MAX_INPUT_SELECTOR,
              maxValue: String(filters.followerFilters.followerCountMax),
              timeoutMs: 10000,
              intervalMs: 250,
              triggerPostClickWaitMs: 300,
              fillPostWaitMs: 200,
              closeAfterFill: true,
              ...buildOutreachDismissPayload(dismissText)
            },
            options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
            onError: OUTREACH_STEP_ERROR_POLICY
          })
        }
        continue
      }

      if (filterKey === 'gmvSelections' || filterKey === 'itemsSoldSelections') {
        const optionTexts =
          filterKey === 'gmvSelections'
            ? normalizeMultiSelectOptions(
                filters.performanceFilters.gmvSelections,
                PERFORMANCE_GMV_OPTIONS,
                'GMV'
              )
            : normalizeMultiSelectOptions(
                filters.performanceFilters.itemsSoldSelections,
                PERFORMANCE_ITEMS_SOLD_OPTIONS,
                'Items sold'
              )
        if (optionTexts.length && actionType === 'selectDropdownMultiple') {
          moduleFilterSteps.push({
            actionType: 'selectDropdownMultiple',
            payload: {
              triggerText,
              triggerFallbackTexts,
              triggerSelector,
              optionTexts,
              optionSelector: optionSelector || MULTI_SELECT_OPTION_SELECTOR,
              waitSelector: waitSelector || MULTI_SELECT_POPUP_SELECTOR,
              waitState: 'visible',
              exact: true,
              caseSensitive: false,
              scrollContainerSelector: scrollContainerSelector || POPUP_SCROLL_CONTAINER_SELECTOR,
              timeoutMs: 10000,
              intervalMs: 250,
              triggerPostClickWaitMs: 300,
              optionPostClickWaitMs: 180,
              closeAfterSelect: true,
              ...buildOutreachDismissPayload(dismissText)
            },
            options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
            onError: OUTREACH_STEP_ERROR_POLICY
          })
        }
        continue
      }

      if (
        filterKey === 'averageViewsPerVideoMin' ||
        filterKey === 'averageViewersPerLiveMin' ||
        filterKey === 'engagementRateMinPercent'
      ) {
        const thresholdConfig =
          filterKey === 'averageViewsPerVideoMin'
            ? {
                value: String(filters.performanceFilters.averageViewsPerVideoMin),
                enabled:
                  String(filters.performanceFilters.averageViewsPerVideoMin).trim() !== '0' ||
                  filters.performanceFilters.averageViewsPerVideoShoppableVideosOnly,
                checkbox:
                  filters.performanceFilters.averageViewsPerVideoShoppableVideosOnly,
                defaultCheckboxLabel: 'Filter by shoppable videos'
              }
            : filterKey === 'averageViewersPerLiveMin'
              ? {
                  value: String(filters.performanceFilters.averageViewersPerLiveMin),
                  enabled:
                    String(filters.performanceFilters.averageViewersPerLiveMin).trim() !== '0' ||
                    filters.performanceFilters.averageViewersPerLiveShoppableLiveOnly,
                  checkbox:
                    filters.performanceFilters.averageViewersPerLiveShoppableLiveOnly,
                  defaultCheckboxLabel: 'Filter by shoppable LIVE streams'
                }
              : {
                  value: String(filters.performanceFilters.engagementRateMinPercent),
                  enabled:
                    String(filters.performanceFilters.engagementRateMinPercent).trim() !== '0' ||
                    filters.performanceFilters.engagementRateShoppableVideosOnly,
                  checkbox:
                    filters.performanceFilters.engagementRateShoppableVideosOnly,
                  defaultCheckboxLabel: 'Filter by shoppable videos'
                }

        if (thresholdConfig.enabled && actionType === 'fillDropdownThreshold') {
          const checkboxLabelText = thresholdConfig.checkbox
            ? resolveThresholdCheckboxLabel(filterKey, filterSpec) ||
              thresholdConfig.defaultCheckboxLabel
            : undefined
          moduleFilterSteps.push({
            actionType: 'fillDropdownThreshold',
            payload: {
              triggerText,
              triggerFallbackTexts,
              triggerSelector,
              waitSelector: waitSelector || POPUP_THRESHOLD_INPUT_SELECTOR,
              inputSelector:
                readScriptText(binding, 'inputSelector', 'input_selector') ||
                POPUP_THRESHOLD_INPUT_SELECTOR,
              value: thresholdConfig.value,
              checkboxLabelText,
              checkboxLabelSelector: checkboxLabelText
                ? readScriptText(binding, 'checkboxLabelSelector', 'checkbox_label_selector') ||
                  POPUP_CHECKBOX_LABEL_SELECTOR
                : undefined,
              checkboxExact: false,
              timeoutMs: 10000,
              intervalMs: 250,
              triggerPostClickWaitMs: 300,
              fillPostWaitMs: 120,
              checkboxPostClickWaitMs: 150,
              closeAfterFill: true,
              ...buildOutreachDismissPayload(dismissText)
            },
            options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
            onError: OUTREACH_STEP_ERROR_POLICY
          })
        }
        continue
      }

      if (filterKey === 'estPostRate') {
        const optionText = normalizeSingleSelectOption(
          filters.performanceFilters.estPostRate,
          PERFORMANCE_EST_POST_RATE_OPTIONS,
          'Est. post rate'
        )
        if (optionText !== 'All' && actionType === 'selectDropdownSingle') {
          moduleFilterSteps.push({
            actionType: 'selectDropdownSingle',
            payload: {
              triggerText,
              triggerFallbackTexts,
              triggerSelector,
              optionText,
              optionSelector: optionSelector || SINGLE_SELECT_OPTION_SELECTOR,
              waitSelector: waitSelector || SINGLE_SELECT_OPTION_SELECTOR,
              waitState: 'visible',
              exact: true,
              caseSensitive: false,
              timeoutMs: 10000,
              intervalMs: 250,
              triggerPostClickWaitMs: 250,
              optionPostClickWaitMs: 160,
              closeAfterSelect: true,
              ...buildOutreachDismissPayload(dismissText)
            },
            options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
            onError: OUTREACH_STEP_ERROR_POLICY
          })
        }
        continue
      }

      if (filterKey === 'brandCollaborationSelections') {
        const optionTexts = normalizeFreeformSelections(
          filters.performanceFilters.brandCollaborationSelections
        )
        if (optionTexts.length && actionType === 'selectDropdownMultiple') {
          moduleFilterSteps.push({
            actionType: 'selectDropdownMultiple',
            payload: {
              triggerText,
              triggerFallbackTexts,
              triggerSelector,
              optionTexts,
              optionSelector: optionSelector || MULTI_SELECT_OPTION_SELECTOR,
              waitSelector: waitSelector || MULTI_SELECT_POPUP_SELECTOR,
              waitState: 'visible',
              exact: true,
              caseSensitive: false,
              scrollContainerSelector: scrollContainerSelector || POPUP_SCROLL_CONTAINER_SELECTOR,
              scrollStepPx: 420,
              maxScrollAttempts: 40,
              timeoutMs: 10000,
              intervalMs: 250,
              triggerPostClickWaitMs: 300,
              optionPostClickWaitMs: 180,
              closeAfterSelect: true,
              continueOnMissingOptions: true,
              ...buildOutreachDismissPayload(dismissText)
            },
            options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
            onError: OUTREACH_STEP_ERROR_POLICY
          })
        }
      }
    }

    if (moduleFilterSteps.length) {
      allSteps.push(
        buildModuleButtonAction(
          moduleTitle,
          350,
          readScriptText(moduleButton, 'selector') || moduleButtonSelector,
          MODULE_BUTTON_FALLBACK_TEXTS[moduleTitle] ?? []
        ),
        ...moduleFilterSteps
      )
    }
  }

  if (!allSteps.length) {
    return null
  }

  const searchBinding = asRecord(readScriptValue(script, 'searchBinding', 'search_binding'))
  return [
    ...allSteps,
    ...buildSearchKeywordStepsFromScript(filters.searchKeyword, searchBinding, dismissText),
    ...buildCreatorCollectionSteps()
  ]
}

export const isOutreachFilterScriptLike = (value: unknown): value is ScriptRecord =>
  Boolean(asRecord(value) && asArray(readScriptValue(asRecord(value), 'modules')).length)

export const resolveOutreachPageReadyText = (script?: ScriptRecord | null): string =>
  readScriptText(asRecord(readScriptValue(script ?? null, 'source')), 'pageReadyText', 'page_ready_text') ||
  OUTREACH_FILTER_DISMISS_TEXT

export const buildOutreachFilterStepsFromScript = (
  filters: OutreachFilterConfig,
  script?: ScriptRecord | null
): BrowserAction[] | null => {
  if (!script) {
    return null
  }
  return buildScriptDrivenFilterSteps(filters, script)
}

const buildCreatorFilterSteps = (config: CreatorFilterConfig): BrowserAction[] => {
  const categoryValues = normalizeCreatorProductCategoryValues(config.productCategorySelections)
  const avgCommissionRate = normalizeSingleSelectOption(config.avgCommissionRate, AVG_COMMISSION_RATE_OPTIONS, 'Avg. commission rate')
  const contentType = normalizeSingleSelectOption(config.contentType, CONTENT_TYPE_OPTIONS, 'Content type')
  const creatorAgency = normalizeSingleSelectOption(config.creatorAgency, CREATOR_AGENCY_OPTIONS, 'Creator agency')

  const filterSteps: BrowserAction[] = []

  if (categoryValues.length) {
    filterSteps.push({
      actionType: 'selectCascaderOptionsByValue',
      payload: {
        triggerText: 'Product category',
        triggerSelector: FILTER_TITLE_SELECTOR,
        panelSelector: PRODUCT_CATEGORY_PANEL_SELECTOR,
        values: categoryValues,
        inputSelector: 'input[type="checkbox"]',
        scrollContainerSelector: PRODUCT_CATEGORY_PANEL_SELECTOR,
        scrollStepPx: 320,
        maxScrollAttempts: 20,
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 300,
        optionPostClickWaitMs: 180,
        closeAfterSelect: true
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (avgCommissionRate !== 'All') {
    filterSteps.push({
      actionType: 'selectDropdownSingle',
      payload: {
        triggerText: 'Avg. commission rate',
        triggerSelector: FILTER_TITLE_SELECTOR,
        optionText: avgCommissionRate,
        optionSelector: SINGLE_SELECT_OPTION_SELECTOR,
        waitSelector: SINGLE_SELECT_OPTION_SELECTOR,
        waitState: 'visible',
        exact: true,
        caseSensitive: false,
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 250,
        optionPostClickWaitMs: 160,
        closeAfterSelect: true,
        ...buildOutreachDismissPayload()
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (contentType !== 'All') {
    filterSteps.push({
      actionType: 'selectDropdownSingle',
      payload: {
        triggerText: 'Content type',
        triggerSelector: FILTER_TITLE_SELECTOR,
        optionText: contentType,
        optionSelector: SINGLE_SELECT_OPTION_SELECTOR,
        waitSelector: SINGLE_SELECT_OPTION_SELECTOR,
        waitState: 'visible',
        exact: true,
        caseSensitive: false,
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 250,
        optionPostClickWaitMs: 160,
        closeAfterSelect: true,
        ...buildOutreachDismissPayload()
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (creatorAgency !== 'All') {
    filterSteps.push({
      actionType: 'selectDropdownSingle',
      payload: {
        triggerText: 'Creator agency',
        triggerSelector: FILTER_TITLE_SELECTOR,
        optionText: creatorAgency,
        optionSelector: SINGLE_SELECT_OPTION_SELECTOR,
        waitSelector: SINGLE_SELECT_OPTION_SELECTOR,
        waitState: 'visible',
        exact: true,
        caseSensitive: false,
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 250,
        optionPostClickWaitMs: 160,
        closeAfterSelect: true,
        ...buildOutreachDismissPayload()
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (config.spotlightCreator) {
    filterSteps.push({
      id: '勾选 Spotlight Creator',
      actionType: 'setCheckbox',
      payload: {
        selector: 'label#isRisingStar_input',
        checked: true,
        timeoutMs: 10000,
        intervalMs: 250,
        scrollContainerSelector: OUTREACH_SCROLL_CONTAINER_SELECTOR,
        scrollStepPx: 420,
        maxScrollAttempts: 20,
        postClickWaitMs: 150
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (config.fastGrowing) {
    filterSteps.push({
      id: '勾选 Fast growing',
      actionType: 'setCheckbox',
      payload: {
        selector: 'label#isFastGrowing_input',
        checked: true,
        timeoutMs: 10000,
        intervalMs: 250,
        scrollContainerSelector: OUTREACH_SCROLL_CONTAINER_SELECTOR,
        scrollStepPx: 420,
        maxScrollAttempts: 20,
        postClickWaitMs: 150
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (config.notInvitedInPast90Days) {
    filterSteps.push({
      id: '勾选 Not invited in past 90 days',
      actionType: 'setCheckbox',
      payload: {
        selector: 'label#isInvitedBefore_input',
        checked: true,
        timeoutMs: 10000,
        intervalMs: 250,
        scrollContainerSelector: OUTREACH_SCROLL_CONTAINER_SELECTOR,
        scrollStepPx: 420,
        maxScrollAttempts: 20,
        postClickWaitMs: 150
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  return filterSteps.length ? [buildModuleButtonAction('Creators'), ...filterSteps] : []
}

const buildFollowerFilterSteps = (config: FollowerFilterConfig): BrowserAction[] => {
  const followerAgeSelections = normalizeMultiSelectOptions(config.followerAgeSelections, FOLLOWER_AGE_OPTIONS, 'Follower age')
  const followerGender = normalizeSingleSelectOption(config.followerGender, FOLLOWER_GENDER_OPTIONS, 'Follower gender')
  const hasFollowerCountOverride =
    String(config.followerCountMin).trim() !== '0' || String(config.followerCountMax).trim() !== '10,000,000+'

  const filterSteps: BrowserAction[] = []

  if (followerAgeSelections.length) {
    filterSteps.push({
      actionType: 'selectDropdownMultiple',
      payload: {
        triggerText: 'Follower age',
        triggerSelector: FILTER_TITLE_SELECTOR,
        optionTexts: followerAgeSelections,
        optionSelector: MULTI_SELECT_OPTION_SELECTOR,
        waitSelector: MULTI_SELECT_POPUP_SELECTOR,
        waitState: 'visible',
        exact: true,
        caseSensitive: false,
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 300,
        optionPostClickWaitMs: 180,
        closeAfterSelect: true,
        ...buildOutreachDismissPayload()
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (followerGender !== 'All') {
    filterSteps.push({
      actionType: 'selectDropdownSingle',
      payload: {
        triggerText: 'Follower gender',
        triggerSelector: FILTER_TITLE_SELECTOR,
        optionText: followerGender,
        optionSelector: SINGLE_SELECT_OPTION_SELECTOR,
        waitSelector: SINGLE_SELECT_OPTION_SELECTOR,
        waitState: 'visible',
        exact: true,
        caseSensitive: false,
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 250,
        optionPostClickWaitMs: 160,
        closeAfterSelect: true,
        ...buildOutreachDismissPayload()
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (hasFollowerCountOverride) {
    filterSteps.push({
      actionType: 'fillDropdownRange',
      payload: {
        triggerText: 'Follower count',
        triggerFallbackTexts: ['Follower c'],
        triggerSelector: FILTER_TITLE_SELECTOR,
        triggerExact: false,
        waitSelector: FOLLOWER_COUNT_RANGE_SELECTOR,
        minSelector: FOLLOWER_COUNT_MIN_INPUT_SELECTOR,
        minValue: String(config.followerCountMin),
        maxSelector: FOLLOWER_COUNT_MAX_INPUT_SELECTOR,
        maxValue: String(config.followerCountMax),
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 300,
        fillPostWaitMs: 200,
        closeAfterFill: true,
        ...buildOutreachDismissPayload()
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  return filterSteps.length ? [buildModuleButtonAction('Followers'), ...filterSteps] : []
}

const buildPerformanceFilterSteps = (config: PerformanceFilterConfig): BrowserAction[] => {
  const gmvSelections = normalizeMultiSelectOptions(config.gmvSelections, PERFORMANCE_GMV_OPTIONS, 'GMV')
  const itemsSoldSelections = normalizeMultiSelectOptions(config.itemsSoldSelections, PERFORMANCE_ITEMS_SOLD_OPTIONS, 'Items sold')
  const estPostRate = normalizeSingleSelectOption(config.estPostRate, PERFORMANCE_EST_POST_RATE_OPTIONS, 'Est. post rate')
  const brandCollaborationSelections = normalizeFreeformSelections(config.brandCollaborationSelections)

  const hasAverageViewsPerVideoOverride =
    String(config.averageViewsPerVideoMin).trim() !== '0' || config.averageViewsPerVideoShoppableVideosOnly
  const hasAverageViewersPerLiveOverride =
    String(config.averageViewersPerLiveMin).trim() !== '0' || config.averageViewersPerLiveShoppableLiveOnly
  const hasEngagementRateOverride =
    String(config.engagementRateMinPercent).trim() !== '0' || config.engagementRateShoppableVideosOnly

  const filterSteps: BrowserAction[] = []

  if (gmvSelections.length) {
    filterSteps.push({
      actionType: 'selectDropdownMultiple',
      payload: {
        triggerText: 'GMV',
        triggerSelector: FILTER_TITLE_SELECTOR,
        optionTexts: gmvSelections,
        optionSelector: MULTI_SELECT_OPTION_SELECTOR,
        waitSelector: MULTI_SELECT_POPUP_SELECTOR,
        waitState: 'visible',
        exact: true,
        caseSensitive: false,
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 300,
        optionPostClickWaitMs: 180,
        closeAfterSelect: true,
        ...buildOutreachDismissPayload()
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (itemsSoldSelections.length) {
    filterSteps.push({
      actionType: 'selectDropdownMultiple',
      payload: {
        triggerText: 'Items sold',
        triggerSelector: FILTER_TITLE_SELECTOR,
        optionTexts: itemsSoldSelections,
        optionSelector: MULTI_SELECT_OPTION_SELECTOR,
        waitSelector: MULTI_SELECT_POPUP_SELECTOR,
        waitState: 'visible',
        exact: true,
        caseSensitive: false,
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 300,
        optionPostClickWaitMs: 180,
        closeAfterSelect: true,
        ...buildOutreachDismissPayload()
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (hasAverageViewsPerVideoOverride) {
    filterSteps.push({
      actionType: 'fillDropdownThreshold',
      payload: {
        triggerText: 'Average views per video',
        triggerSelector: FILTER_TITLE_SELECTOR,
        waitSelector: POPUP_THRESHOLD_INPUT_SELECTOR,
        inputSelector: POPUP_THRESHOLD_INPUT_SELECTOR,
        value: String(config.averageViewsPerVideoMin),
        checkboxLabelText: config.averageViewsPerVideoShoppableVideosOnly ? 'Filter by shoppable videos' : undefined,
        checkboxLabelSelector: config.averageViewsPerVideoShoppableVideosOnly ? POPUP_CHECKBOX_LABEL_SELECTOR : undefined,
        checkboxExact: false,
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 300,
        fillPostWaitMs: 120,
        checkboxPostClickWaitMs: 150,
        closeAfterFill: true,
        ...buildOutreachDismissPayload()
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (hasAverageViewersPerLiveOverride) {
    filterSteps.push({
      actionType: 'fillDropdownThreshold',
      payload: {
        triggerText: 'Average viewers per LIVE',
        triggerSelector: FILTER_TITLE_SELECTOR,
        waitSelector: POPUP_THRESHOLD_INPUT_SELECTOR,
        inputSelector: POPUP_THRESHOLD_INPUT_SELECTOR,
        value: String(config.averageViewersPerLiveMin),
        checkboxLabelText: config.averageViewersPerLiveShoppableLiveOnly ? 'Filter by shoppable LIVE streams' : undefined,
        checkboxLabelSelector: config.averageViewersPerLiveShoppableLiveOnly ? POPUP_CHECKBOX_LABEL_SELECTOR : undefined,
        checkboxExact: false,
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 300,
        fillPostWaitMs: 120,
        checkboxPostClickWaitMs: 150,
        closeAfterFill: true,
        ...buildOutreachDismissPayload()
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (hasEngagementRateOverride) {
    filterSteps.push({
      actionType: 'fillDropdownThreshold',
      payload: {
        triggerText: 'Engagement rate',
        triggerSelector: FILTER_TITLE_SELECTOR,
        waitSelector: POPUP_THRESHOLD_INPUT_SELECTOR,
        inputSelector: POPUP_THRESHOLD_INPUT_SELECTOR,
        value: String(config.engagementRateMinPercent),
        checkboxLabelText: config.engagementRateShoppableVideosOnly ? 'Filter by shoppable videos' : undefined,
        checkboxLabelSelector: config.engagementRateShoppableVideosOnly ? POPUP_CHECKBOX_LABEL_SELECTOR : undefined,
        checkboxExact: false,
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 300,
        fillPostWaitMs: 120,
        checkboxPostClickWaitMs: 150,
        closeAfterFill: true,
        ...buildOutreachDismissPayload()
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (estPostRate !== 'All') {
    filterSteps.push({
      actionType: 'selectDropdownSingle',
      payload: {
        triggerText: 'Est. post rate',
        triggerSelector: FILTER_TITLE_SELECTOR,
        optionText: estPostRate,
        optionSelector: SINGLE_SELECT_OPTION_SELECTOR,
        waitSelector: SINGLE_SELECT_OPTION_SELECTOR,
        waitState: 'visible',
        exact: true,
        caseSensitive: false,
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 250,
        optionPostClickWaitMs: 160,
        closeAfterSelect: true,
        ...buildOutreachDismissPayload()
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  if (brandCollaborationSelections.length) {
    filterSteps.push({
      actionType: 'selectDropdownMultiple',
      payload: {
        triggerText: 'Brand collaborations',
        triggerSelector: FILTER_TITLE_SELECTOR,
        optionTexts: brandCollaborationSelections,
        optionSelector: MULTI_SELECT_OPTION_SELECTOR,
        waitSelector: MULTI_SELECT_POPUP_SELECTOR,
        waitState: 'visible',
        exact: true,
        caseSensitive: false,
        scrollContainerSelector: POPUP_SCROLL_CONTAINER_SELECTOR,
        scrollStepPx: 420,
        maxScrollAttempts: 40,
        timeoutMs: 10000,
        intervalMs: 250,
        triggerPostClickWaitMs: 300,
        optionPostClickWaitMs: 180,
        closeAfterSelect: true,
        ...buildOutreachDismissPayload(),
        continueOnMissingOptions: true
      },
      options: { retryCount: OUTREACH_STEP_RETRY_COUNT },
      onError: OUTREACH_STEP_ERROR_POLICY
    })
  }

  return filterSteps.length ? [buildModuleButtonAction('Performance'), ...filterSteps] : []
}

const buildSearchKeywordSteps = (keyword: string): BrowserAction[] => {
  const normalizedKeyword = String(keyword || '').trim()

  return [
    {
      actionType: 'startJsonResponseCapture',
      payload: {
        captureKey: CREATOR_MARKETPLACE_CAPTURE_KEY,
        urlIncludes: CREATOR_MARKETPLACE_FIND_URL_KEYWORD,
        method: 'POST',
        reset: true
      },
      options: { retryCount: 1 },
      onError: 'abort'
    },
    {
      actionType: 'fillSelector',
      payload: {
        selector: SEARCH_INPUT_SELECTOR,
        value: normalizedKeyword,
        waitForState: 'visible',
        timeoutMs: 10000,
        intervalMs: 250,
        clearBeforeFill: true,
        postFillWaitMs: 120
      },
      options: { retryCount: 2 },
      onError: 'abort'
    },
    {
      actionType: 'clickByText',
      payload: {
        text: OUTREACH_FILTER_DISMISS_TEXT,
        selector: OUTREACH_FILTER_DISMISS_SELECTOR,
        exact: true,
        caseSensitive: false,
        timeoutMs: 10000,
        intervalMs: 250,
        postClickWaitMs: 120
      },
      options: { retryCount: 2 },
      onError: 'abort'
    },
    {
      actionType: 'clickSelector',
      payload: {
        selector: SEARCH_INPUT_SELECTOR,
        waitForState: 'visible',
        timeoutMs: 5000,
        intervalMs: 250,
        postClickWaitMs: 80
      },
      options: { retryCount: 2 },
      onError: 'abort'
    },
    {
      actionType: 'pressKey',
      payload: {
        key: 'Enter',
        postKeyWaitMs: 3000
      },
      options: { retryCount: 1 },
      onError: 'abort'
    }
  ]
}

const buildCreatorCollectionSteps = (): BrowserAction[] => [
  {
    actionType: 'collectApiItemsByScrolling',
    payload: {
      captureKey: CREATOR_MARKETPLACE_CAPTURE_KEY,
      responseListPath: 'creator_profile_list',
      dedupeByPath: 'creator_oecuid.value',
      fields: [
        {
          key: 'creator_id',
          path: 'creator_oecuid.value',
          defaultValue: ''
        },
        {
          key: 'avatar_url',
          path: 'avatar.value.thumb_url_list.0',
          defaultValue: ''
        },
        {
          key: 'category',
          path: 'category.value',
          arrayItemPath: 'name',
          joinWith: ',',
          defaultValue: ''
        },
        {
          key: 'creator_name',
          path: 'handle.value',
          defaultValue: ''
        }
      ],
      initialWaitMs: 2000,
      scrollContainerSelector: OUTREACH_SCROLL_CONTAINER_SELECTOR,
      scrollStepPx: 1400,
      scrollIntervalMs: 1800,
      settleWaitMs: 1500,
      maxIdleRounds: 3,
      maxScrollRounds: 200,
      saveAs: CREATOR_MARKETPLACE_DATA_KEY,
      saveSummaryAs: CREATOR_MARKETPLACE_SUMMARY_KEY,
      saveFilePathAs: CREATOR_MARKETPLACE_FILE_PATH_KEY,
      saveExcelFilePathAs: CREATOR_MARKETPLACE_EXCEL_FILE_PATH_KEY,
      saveRawItemsAs: CREATOR_MARKETPLACE_RAW_DATA_KEY,
      saveRawFilePathAs: CREATOR_MARKETPLACE_RAW_FILE_PATH_KEY,
      saveRawDirectoryPathAs: CREATOR_MARKETPLACE_RAW_DIRECTORY_PATH_KEY,
      outputDir: 'data/outreach',
      outputFilePrefix: 'creator_marketplace',
      excelOutputDir: 'data/outreach',
      excelOutputFilePrefix: 'creator_marketplace',
      rawOutputDir: 'data/outreach',
      rawOutputFilePrefix: 'creator_marketplace_raw',
      rawDirectoryOutputDir: 'data/outreach',
      rawDirectoryOutputPrefix: 'creator_marketplace_raw_items'
    },
    options: { retryCount: 1 },
    onError: 'abort'
  }
]

export const buildOutreachFilterSteps = (filters: OutreachFilterConfig): BrowserAction[] => [
  ...buildCreatorFilterSteps(filters.creatorFilters),
  ...buildFollowerFilterSteps(filters.followerFilters),
  ...buildPerformanceFilterSteps(filters.performanceFilters),
  ...buildSearchKeywordSteps(filters.searchKeyword),
  ...buildCreatorCollectionSteps()
]
