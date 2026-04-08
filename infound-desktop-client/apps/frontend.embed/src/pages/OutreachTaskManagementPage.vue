<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { createDiscreteApi, NCard, NModal } from 'naive-ui'
import CreateOutreachTaskModal, {
  type CreateOutreachTaskFilterOptions,
  type CreateOutreachTaskFormPayload,
  type SelectOptionItem
} from '../components/CreateOutreachTaskModal.vue'
import OutreachTaskDetailView from '../components/OutreachTaskDetailView.vue'
import {
  createOutreachTask,
  editOutreachTask,
  getOutreachCreatorFilterItems,
  getOutreachTaskDetail,
  getOutreachTaskList,
  startOutreachTask,
  stopOutreachTask,
  type CreatorFilterOption,
  type CreatorFilterTreeOption,
  type CreateOutreachTaskPayload,
  type EditOutreachTaskPayload,
  type OutreachCreatorFilterItemsResult,
  type OutreachTaskItem as ApiOutreachTaskItem
} from '../api/outreach-task.api'

type TaskStatus = '运行中' | '未启动' | '已结束' | '已完成' | '已取消'
type FilterTaskStatus = '' | '运行中' | '已完成' | '已取消' | '未启动'
type TaskPageView = 'list' | 'create' | 'edit' | 'detail'
type TaskAction = 'view' | 'start' | 'end' | 'copy' | 'edit'

interface OutreachTaskItem {
  id: string
  taskName: string
  startTime: string
  planCount: number
  linkedCount: number
  duration: string
  spendTime: number
  status: TaskStatus
  raw: Record<string, any>
}

interface HashRoute {
  view: TaskPageView
  taskId?: string
  copyFrom?: string
}

const props = defineProps<{
  shopId?: string
}>()

const { dialog, message } = createDiscreteApi(['dialog', 'message'])

const keywordInput = ref('')
const statusInput = ref<FilterTaskStatus>('')
const keywordQuery = ref('')
const statusQuery = ref<FilterTaskStatus>('')
const page = ref(1)
const pageSize = ref(10)
const pageSizeOptions = [10, 20, 50]
const durationNow = ref(Date.now())
let durationTimer: ReturnType<typeof window.setInterval> | null = null

const taskList = ref<OutreachTaskItem[]>([])
const total = ref(0)
const isLoading = ref(false)
const errorMessage = ref('')
const emptyMessage = ref('暂无任务数据')
const currentView = ref<TaskPageView>('list')
const activeTaskId = ref('')
const formInitialData = ref<Partial<CreateOutreachTaskFormPayload> | undefined>(undefined)
const isTaskFormDirty = ref(false)
const isFormSubmitting = ref(false)
const formErrorMessage = ref('')
const maxPlanCount = ref(200)
const taskFilterOptions = ref<CreateOutreachTaskFilterOptions | undefined>(undefined)

const taskFormCache = ref<Record<string, CreateOutreachTaskFormPayload>>({})
const isRestoringHash = ref(false)
const allowNextHashNavigationWithoutConfirm = ref(false)
const lastHash = ref('#/outreach')
const pendingLeaveRoute = ref<HashRoute | null>(null)
const isLeaveDialogOpen = ref(false)

const TASK_CACHE_PREFIX = 'embed-outreach-task:'

const statusOptions: FilterTaskStatus[] = ['', '运行中', '已完成', '已取消', '未启动']

const FILTER_UI_TO_API_STATUS: Record<Exclude<FilterTaskStatus, ''>, string> = {
  运行中: 'RUNNING',
  已完成: 'COMPLETED',
  已取消: 'CANCELLED',
  未启动: 'PENDING'
}

const PERFORMANCE_EST_POST_RATE_OPTIONS = ['All', 'OK', 'Good', 'Better']
const SORT_OPTION_VALUES = ['OFFICIAL_DEFAULT', 'GMV_DESC', 'FOLLOWERS_DESC', 'COMMISSION_DESC']

const ACTION_META: Record<TaskAction, { icon: string; title: string }> = {
  view: { icon: '👁', title: '查看' },
  start: { icon: '▶', title: '启动' },
  end: { icon: '⏸', title: '结束' },
  copy: { icon: '⧉', title: '复制' },
  edit: { icon: '✎', title: '编辑' }
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const activeTask = computed<OutreachTaskItem | null>(() => {
  if (!activeTaskId.value) return null
  return resolveTaskById(activeTaskId.value) || null
})

const formTitle = computed(() => {
  if (currentView.value === 'edit') return '编辑任务'
  if (currentView.value === 'create' && formInitialData.value) return '复制任务'
  return '新增任务'
})

const isTaskFormView = computed(() => currentView.value === 'create' || currentView.value === 'edit')
const isTaskModalVisible = computed(() => currentView.value !== 'list')
const isDetailModalVisible = computed(() => currentView.value === 'detail')
const isTaskFormModalVisible = computed(() => currentView.value === 'create' || currentView.value === 'edit')
const hasUnsavedTaskFormChanges = computed(() => isTaskFormView.value && isTaskFormDirty.value)

const sanitizeKeyword = (value: string): string => {
  return value.trim().slice(0, 20)
}

const normalizeStatusToUI = (value: string): TaskStatus => {
  const source = (value || '').trim()
  const normalized = source.toUpperCase()

  if (normalized === 'RUNNING' || source === '运行中') return '运行中'
  if (normalized === 'PENDING' || normalized === 'NOT_STARTED' || source === '未启动') return '未启动'
  if (normalized === 'COMPLETED' || source === '已完成') return '已完成'
  if (normalized === 'ENDED' || normalized === 'STOPPED' || source === '已结束') return '已结束'
  if (normalized === 'CANCELED' || normalized === 'CANCELLED' || source === '已取消') return '已取消'

  return '未启动'
}

const normalizeTaskItem = (item: ApiOutreachTaskItem): OutreachTaskItem => {
  return {
    id: item.id,
    taskName: item.taskName,
    startTime: item.startTime,
    planCount: item.planCount,
    linkedCount: item.linkedCount,
    duration: item.duration,
    spendTime: item.spendTime,
    status: normalizeStatusToUI(item.status),
    raw: item as unknown as Record<string, any>
  }
}

const formatDurationText = (seconds: number): string => {
  const safeSeconds = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(safeSeconds / 3600)
  const minutes = Math.floor((safeSeconds % 3600) / 60)
  const remainSeconds = safeSeconds % 60

  if (hours > 0) return `${hours}时${minutes}分${remainSeconds}秒`
  if (minutes > 0) return `${minutes}分${remainSeconds}秒`
  return `${remainSeconds}秒`
}

const toElapsedSecondsFromStartTime = (startTime: string): number => {
  const parsed = new Date(String(startTime || ''))
  const startAt = parsed.getTime()
  if (Number.isNaN(startAt)) return 0
  return Math.max(0, Math.floor((durationNow.value - startAt) / 1000))
}

const getTaskDurationText = (task: OutreachTaskItem): string => {
  const fixedDurationText = String(task.duration || '').trim()
  const spendTimeSeconds = Number(task.spendTime || 0)

  if (task.status === '运行中') {
    const elapsedSeconds = toElapsedSecondsFromStartTime(task.startTime)
    const displaySeconds = Math.max(spendTimeSeconds, elapsedSeconds)
    return formatDurationText(displaySeconds)
  }

  if (spendTimeSeconds > 0) {
    return formatDurationText(spendTimeSeconds)
  }

  return fixedDurationText || '-'
}

const getRowIndex = (index: number): number => {
  return (page.value - 1) * pageSize.value + index + 1
}

const getStatusClass = (status: TaskStatus): string => {
  if (status === '运行中') return 'is-running'
  if (status === '未启动') return 'is-pending'
  if (status === '已完成') return 'is-completed'
  if (status === '已取消' || status === '已结束') return 'is-ended'
  return 'is-pending'
}

const getTaskActions = (status: TaskStatus): TaskAction[] => {
  if (status === '未启动') return ['start', 'edit', 'view', 'copy']
  if (status === '运行中') return ['end', 'view', 'copy']
  return ['view', 'copy']
}

const matchesKeyword = (task: OutreachTaskItem, keyword: string): boolean => {
  if (!keyword) return true
  return task.taskName.toLowerCase().includes(keyword.toLowerCase())
}

const matchesStatus = (task: OutreachTaskItem, status: FilterTaskStatus): boolean => {
  if (!status) return true
  if (status === '已取消') {
    return task.status === '已取消' || task.status === '已结束'
  }
  return task.status === status
}

const applyTaskFilters = (source: OutreachTaskItem[]): OutreachTaskItem[] => {
  return source.filter((item) => {
    return matchesKeyword(item, keywordQuery.value) && matchesStatus(item, statusQuery.value)
  })
}

const toJoinedString = (values: string[]): string => {
  return values.map((item) => String(item).trim()).filter(Boolean).join(',')
}

const toTrimmedList = (values: string[]): string[] => {
  return values.map((item) => String(item).trim()).filter(Boolean)
}

const toCompactInteger = (value: string): number => {
  const normalized = String(value || '')
    .trim()
    .replace(/,/g, '')
    .replace(/\s+/g, '')
    .replace(/\+/g, '')

  if (!normalized) return 0

  const compactMatch = normalized.match(/^(\d+(?:\.\d+)?)([kKmM])$/)
  if (compactMatch) {
    const base = Number(compactMatch[1])
    const suffix = compactMatch[2]?.toUpperCase()
    if (!Number.isFinite(base)) return 0
    if (suffix === 'K') return Math.round(base * 1000)
    if (suffix === 'M') return Math.round(base * 1000000)
  }

  const direct = Number(normalized)
  return Number.isFinite(direct) ? Math.round(direct) : 0
}

const toCreatorCountRange = (min: string, max: string): { min: string; max: string } => {
  const rawMin = String(min || '').trim()
  const rawMax = String(max || '').trim()
  return {
    min: rawMin ? String(toCompactInteger(rawMin)) : '',
    max: rawMax ? String(toCompactInteger(rawMax)) : ''
  }
}

const normalizeSelectOption = <T extends string | number>(option: CreatorFilterOption<T>): SelectOptionItem<T> => ({
  label: String(option?.label ?? option?.value ?? ''),
  value: option?.value
})

const normalizeOptionKey = (value: string): string => String(value || '').replace(/\s+/g, '').toLowerCase()

const dedupeStringOptions = (options: Array<SelectOptionItem<string>>): Array<SelectOptionItem<string>> => {
  const result = new Map<string, SelectOptionItem<string>>()
  for (const option of options) {
    result.set(normalizeOptionKey(String(option.value)), option)
  }
  return Array.from(result.values())
}

const flattenTreeOptions = (options: CreatorFilterTreeOption[] | undefined): Array<SelectOptionItem<string>> => {
  if (!Array.isArray(options)) return []

  return options.flatMap((item) => {
    const label = String(item?.raw_label || '').trim()
    const fallbackLabel = String(item?.label ?? item?.value ?? '')
    const current: SelectOptionItem<string> = {
      label: label || fallbackLabel,
      value: String(item?.value ?? '')
    }
    const children = flattenTreeOptions(item?.children)
    return [current, ...children]
  })
}

const buildTaskFilterOptions = (payload: OutreachCreatorFilterItemsResult): CreateOutreachTaskFilterOptions => {
  const creators = payload.creators?.filters
  const followers = payload.followers?.filters
  const performance = payload.performance?.filters

  return {
    productCategoryOptions: flattenTreeOptions(creators?.productCategories?.optionTree),
    avgCommissionRateOptions: creators?.avgCommissionRate?.options?.map(normalizeSelectOption) || [],
    contentTypeOptions: creators?.contentTypes?.options?.map(normalizeSelectOption) || [],
    creatorAgencyOptions: creators?.creatorAgency?.options?.map(normalizeSelectOption) || [],
    followerAgeOptions: dedupeStringOptions(followers?.fansAgeRange?.options?.map(normalizeSelectOption) || []),
    followerGenderOptions: followers?.fansGender?.options?.map(normalizeSelectOption) || [],
    followerCountPresetOptions: followers?.fansCountRange?.presetOptions?.map(normalizeSelectOption) || [],
    gmvOptions: performance?.gmvRange?.options?.map(normalizeSelectOption) || [],
    itemsSoldOptions: performance?.salesCountRange?.options?.map(normalizeSelectOption) || [],
    avgVideoViewsPresetOptions: performance?.minAvgVideoViews?.presetOptions?.map(normalizeSelectOption) || [],
    avgLiveViewsPresetOptions: performance?.minAvgLiveViews?.presetOptions?.map(normalizeSelectOption) || [],
    engagementRatePresetOptions: performance?.minEngagementRate?.presetOptions?.map(normalizeSelectOption) || [],
    estPostRateOptions: [],
    sortOptions: performance?.sortBy?.options?.map(normalizeSelectOption) || [],
    avgVideoViewsToggleLabel: String(performance?.minAvgVideoViews?.toggleOptionItems?.[0]?.label || ''),
    avgLiveViewsToggleLabel: String(performance?.minAvgLiveViews?.toggleOptionItems?.[1]?.label || performance?.minAvgLiveViews?.toggleOptionItems?.[0]?.label || ''),
    engagementRateToggleLabel: String(performance?.minEngagementRate?.toggleOptionItems?.[0]?.label || '')
  }
}

const toNumericOptionValue = (
  value: string | number,
  options: Array<SelectOptionItem<string | number>> | undefined,
  fallback: string[]
): number => {
  const effectiveOptions = options?.length ? options : fallback.map((item) => ({ label: item, value: item as string | number }))
  const selectedIndex = effectiveOptions.findIndex((item) => item.value === value)
  if (selectedIndex < 0) return 0

  const selected = effectiveOptions[selectedIndex]
  return typeof selected?.value === 'number' ? selected.value : selectedIndex
}

const toCreateTaskApiPayload = (shopId: string, payload: CreateOutreachTaskFormPayload): CreateOutreachTaskPayload => {
  const creatorFilters = payload.filterConfig.creatorFilters
  const followerFilters = payload.filterConfig.followerFilters
  const performanceFilters = payload.filterConfig.performanceFilters
  const firstMessage = payload.messageTemplate.firstMessage
  const replyMessage = payload.messageTemplate.replyMessage
  const allProductIds = [...firstMessage.productIds, ...(replyMessage?.productIds || [])]
  const uniqueProductIds = Array.from(new Set(allProductIds.map((item) => String(item).trim()).filter(Boolean)))
  const attachProducts =
    Boolean(firstMessage.productMessageEnabled || replyMessage?.productMessageEnabled) && uniqueProductIds.length > 0
  const filterOptions = taskFilterOptions.value

  return {
    shopId,
    taskName: payload.taskName,
    startTime: String(payload.startTime || ''),
    creatorFilter: {
      keyword: payload.filterConfig.searchKeyword,
      productCategories: toTrimmedList(creatorFilters.productCategorySelections),
      avgCommissionRate: toNumericOptionValue(creatorFilters.avgCommissionRate, filterOptions?.avgCommissionRateOptions, []),
      contentTypes: toNumericOptionValue(creatorFilters.contentType, filterOptions?.contentTypeOptions, []),
      creatorAgency: toNumericOptionValue(creatorFilters.creatorAgency, filterOptions?.creatorAgencyOptions, []),
      fastGrowing: creatorFilters.fastGrowing ? '1' : '0',
      notInvitedInPast90Days: creatorFilters.notInvitedInPast90Days ? '1' : '0',
      fansAgeRange: toTrimmedList(followerFilters.followerAgeSelections),
      fansGender: toNumericOptionValue(followerFilters.followerGender, filterOptions?.followerGenderOptions, []),
      fansCountRange: toCreatorCountRange(followerFilters.followerCountMin, followerFilters.followerCountMax),
      gmvRange: toTrimmedList(performanceFilters.gmvSelections),
      salesCountRange: toTrimmedList(performanceFilters.itemsSoldSelections),
      minAvgVideoViews: toCompactInteger(performanceFilters.averageViewsPerVideoMin),
      minAvgLiveViews: toCompactInteger(performanceFilters.averageViewersPerLiveMin),
      minEngagementRate: toCompactInteger(performanceFilters.engagementRateMinPercent),
      creatorEstimatedPublishRate: toNumericOptionValue(performanceFilters.estPostRate, filterOptions?.estPostRateOptions, PERFORMANCE_EST_POST_RATE_OPTIONS),
      coBranding: toTrimmedList(performanceFilters.brandCollaborationSelections),
      sortBy: toNumericOptionValue(payload.creatorSort, filterOptions?.sortOptions, SORT_OPTION_VALUES)
    },
    plannedCount: String(payload.planCount),
    outreachMode: payload.outreachCreatorType,
    firstMessage: firstMessage.content,
    replyMessage: replyMessage?.content || '',
    attachProducts,
    productIds: toJoinedString(uniqueProductIds)
  }
}

const toEditTaskApiPayload = (
  taskId: string,
  shopId: string,
  payload: CreateOutreachTaskFormPayload,
  lastModificationTime: string
): EditOutreachTaskPayload => {
  const basePayload = toCreateTaskApiPayload(shopId, payload)
  if (!taskId.trim()) {
    throw new Error('taskId is required')
  }
  if (!lastModificationTime.trim()) {
    throw new Error('lastModificationTime is required')
  }

  return {
    ...basePayload,
    lastModificationTime: lastModificationTime.trim()
  }
}

const cacheTask = (task: OutreachTaskItem): void => {
  try {
    window.localStorage.setItem(`${TASK_CACHE_PREFIX}${task.id}`, JSON.stringify(task))
  } catch (_error) {
    // ignore cache failures
  }
}

const getCachedTask = (taskId: string): OutreachTaskItem | null => {
  try {
    const value = window.localStorage.getItem(`${TASK_CACHE_PREFIX}${taskId}`)
    if (!value) return null
    const parsed = JSON.parse(value) as OutreachTaskItem
    if (!parsed?.id) return null
    return parsed
  } catch (_error) {
    return null
  }
}

const resolveTaskById = (taskId: string): OutreachTaskItem | undefined => {
  const fromList = taskList.value.find((item) => item.id === taskId)
  if (fromList) return fromList
  const fromCache = getCachedTask(taskId)
  if (fromCache) return fromCache
  return undefined
}

const toFormInitialData = (task: OutreachTaskItem, forCopy: boolean): Partial<CreateOutreachTaskFormPayload> => {
  const cachedPayload = taskFormCache.value[task.id]
  if (cachedPayload) {
    return {
      ...cachedPayload,
      taskName: forCopy ? `${cachedPayload.taskName}-副本` : cachedPayload.taskName
    }
  }

  const sourceTaskName = String(task.raw?.taskName || task.taskName || '')
  const sourcePlanCount = Number(task.raw?.planCount ?? task.planCount ?? 0)
  const sourceStartTime = String(task.raw?.startTime || task.startTime || '')

  return {
    taskName: forCopy ? `${sourceTaskName}-副本` : sourceTaskName,
    planCount: Number.isFinite(sourcePlanCount) ? sourcePlanCount : 0,
    startTime: sourceStartTime,
    creatorSort: task.raw?.creatorSort ?? 'OFFICIAL_DEFAULT',
    outreachCreatorType: task.raw?.outreachCreatorType || 'ALL',
    filterConfig: task.raw?.filterConfig,
    messageTemplate: task.raw?.messageTemplate
  }
}

const getStringOptionValue = (
  value: unknown,
  options: Array<SelectOptionItem<string | number>> | undefined,
  fallback: string[]
): string => {
  const numericValue = Number(value)
  if (Number.isInteger(numericValue) && numericValue >= 0) {
    if (options?.length && numericValue < options.length) {
      return String(options[numericValue]?.value ?? '')
    }
    if (numericValue < fallback.length) {
      return fallback[numericValue] || ''
    }
  }

  return String(value ?? '').trim()
}

const toFormInitialDataFromDetail = (
  detailPayload: Record<string, any>,
  fallbackTask: OutreachTaskItem | undefined,
  forCopy: boolean
): Partial<CreateOutreachTaskFormPayload> => {
  const creatorFilter = detailPayload.creatorFilter || {}
  const filterOptions = taskFilterOptions.value
  const productIds = Array.isArray(detailPayload.productIds)
    ? detailPayload.productIds.map((item: unknown) => String(item).trim()).filter(Boolean)
    : []
  const attachProducts = Boolean(detailPayload.attachProducts)
  const outreachMode = String(detailPayload.outreachMode || fallbackTask?.raw?.outreachMode || 'ALL') as CreateOutreachTaskFormPayload['outreachCreatorType']
  const taskName = String(detailPayload.taskName || fallbackTask?.taskName || '')

  return {
    taskName: forCopy ? `${taskName}-副本` : taskName,
    startTime: String(detailPayload.startTime || fallbackTask?.startTime || ''),
    planCount: Number(detailPayload.plannedCount ?? fallbackTask?.planCount ?? 0) || 0,
    creatorSort: detailPayload.creatorFilter?.sortBy ?? fallbackTask?.raw?.creatorSort ?? 'OFFICIAL_DEFAULT',
    outreachCreatorType: outreachMode,
    filterConfig: {
      searchKeyword: String(creatorFilter.keyword || ''),
      creatorFilters: {
        productCategorySelections: Array.isArray(creatorFilter.productCategories)
          ? creatorFilter.productCategories.map((item: unknown) => String(item)).filter(Boolean)
          : [],
        avgCommissionRate: getStringOptionValue(
          creatorFilter.avgCommissionRate,
          filterOptions?.avgCommissionRateOptions,
          ['All', 'Less than 20%', 'Less than 15%', 'Less than 10%', 'Less than 5%']
        ),
        contentType: getStringOptionValue(creatorFilter.contentTypes, filterOptions?.contentTypeOptions, ['All', 'Video', 'LIVE']),
        creatorAgency: getStringOptionValue(
          creatorFilter.creatorAgency,
          filterOptions?.creatorAgencyOptions,
          ['All', 'Managed by Agency', 'Independent creators']
        ),
        spotlightCreator: false,
        fastGrowing: Boolean(creatorFilter.fastGrowing),
        notInvitedInPast90Days: Boolean(creatorFilter.notInvitedInPast90Days)
      },
      followerFilters: {
        followerAgeSelections: Array.isArray(creatorFilter.fansAgeRange)
          ? creatorFilter.fansAgeRange.map((item: unknown) => String(item)).filter(Boolean)
          : [],
        followerGender: getStringOptionValue(creatorFilter.fansGender, filterOptions?.followerGenderOptions, ['All', 'Female', 'Male']),
        followerCountMin: String(creatorFilter.fansCountRange?.min ?? ''),
        followerCountMax: String(creatorFilter.fansCountRange?.max ?? '')
      },
      performanceFilters: {
        gmvSelections: Array.isArray(creatorFilter.gmvRange) ? creatorFilter.gmvRange.map((item: unknown) => String(item)).filter(Boolean) : [],
        itemsSoldSelections: Array.isArray(creatorFilter.salesCountRange)
          ? creatorFilter.salesCountRange.map((item: unknown) => String(item)).filter(Boolean)
          : [],
        averageViewsPerVideoMin: String(creatorFilter.minAvgVideoViews ?? ''),
        averageViewsPerVideoShoppableVideosOnly: false,
        averageViewersPerLiveMin: String(creatorFilter.minAvgLiveViews ?? ''),
        averageViewersPerLiveShoppableLiveOnly: false,
        engagementRateMinPercent: String(creatorFilter.minEngagementRate ?? ''),
        engagementRateShoppableVideosOnly: false,
        estPostRate: String(creatorFilter.creatorEstimatedPublishRate ?? 'All'),
        brandCollaborationSelections: Array.isArray(creatorFilter.coBranding)
          ? creatorFilter.coBranding.map((item: unknown) => String(item)).filter(Boolean)
          : []
      }
    },
    messageTemplate: {
      firstMessage: {
        content: String(detailPayload.firstMessage || ''),
        productMessageEnabled: attachProducts,
        productIds: [...productIds]
      },
      replyMessage:
        outreachMode === 'ALL'
          ? {
              content: String(detailPayload.replyMessage || ''),
              productMessageEnabled: attachProducts,
              productIds: [...productIds]
            }
          : undefined
    }
  }
}

const loadEditInitialData = async (taskId: string): Promise<void> => {
  const task = resolveTaskById(taskId)

  currentView.value = 'edit'
  activeTaskId.value = taskId
  formErrorMessage.value = ''
  isTaskFormDirty.value = false
  formInitialData.value = task ? toFormInitialData(task, false) : undefined

  try {
    const detailResult = await getOutreachTaskDetail(taskId)
    const detailPayload = (detailResult?.data ?? detailResult ?? {}) as Record<string, any>
    formInitialData.value = toFormInitialDataFromDetail(detailPayload, task, false)
  } catch (_error) {
    if (!task) {
      currentView.value = 'list'
      activeTaskId.value = ''
      formInitialData.value = undefined
      formErrorMessage.value = '未找到要编辑的任务'
      return
    }

    formInitialData.value = toFormInitialData(task, false)
    formErrorMessage.value = '编辑页回填失败，已回退到列表缓存数据'
  }
}

const loadCopyInitialData = async (taskId: string): Promise<void> => {
  const task = resolveTaskById(taskId)

  currentView.value = 'create'
  activeTaskId.value = ''
  formErrorMessage.value = ''
  isTaskFormDirty.value = false
  formInitialData.value = task ? toFormInitialData(task, true) : undefined

  try {
    const detailResult = await getOutreachTaskDetail(taskId)
    const detailPayload = (detailResult?.data ?? detailResult ?? {}) as Record<string, any>
    formInitialData.value = toFormInitialDataFromDetail(detailPayload, task, true)
  } catch (_error) {
    if (!task) {
      formInitialData.value = undefined
      formErrorMessage.value = '未找到复制来源任务，已使用默认值'
      return
    }

    formInitialData.value = toFormInitialData(task, true)
    formErrorMessage.value = '复制任务回填失败，已回退到列表缓存数据'
  }
}

const getTaskLastModificationTime = async (taskId: string): Promise<string> => {
  const detailResult = await getOutreachTaskDetail(taskId)
  const detailPayload = (detailResult?.data ?? detailResult ?? {}) as Record<string, any>
  const lastModificationTime = String(detailPayload.lastModificationTime || '').trim()
  if (!lastModificationTime) {
    throw new Error('缺少 lastModificationTime，无法提交任务操作')
  }
  return lastModificationTime
}

const parseHashRoute = (): HashRoute => {
  const rawHash = window.location.hash || '#/outreach'
  const [pathPart = '', queryPart = ''] = rawHash.replace(/^#/, '').split('?')
  if (!pathPart.toLowerCase().includes('/outreach')) {
    return { view: 'list' }
  }

  const query = new URLSearchParams(queryPart)
  const viewParam = (query.get('view') || 'list').toLowerCase()
  const taskId = query.get('taskId')?.trim() || ''
  const copyFrom = query.get('copyFrom')?.trim() || ''

  if (viewParam === 'create') {
    return {
      view: 'create',
      copyFrom
    }
  }
  if (viewParam === 'edit') {
    return {
      view: 'edit',
      taskId
    }
  }
  if (viewParam === 'detail') {
    return {
      view: 'detail',
      taskId
    }
  }

  return { view: 'list' }
}

const buildHash = (route: HashRoute): string => {
  if (route.view === 'list') {
    return '#/outreach'
  }

  const query = new URLSearchParams()
  query.set('view', route.view)
  if (route.taskId) query.set('taskId', route.taskId)
  if (route.copyFrom) query.set('copyFrom', route.copyFrom)
  return `#/outreach?${query.toString()}`
}

const applyRoute = (route: HashRoute): void => {
  if (route.view === 'list') {
    currentView.value = 'list'
    activeTaskId.value = ''
    formInitialData.value = undefined
    formErrorMessage.value = ''
    isTaskFormDirty.value = false
    return
  }

  if (route.view === 'create') {
    currentView.value = 'create'
    activeTaskId.value = ''
    formErrorMessage.value = ''
    isTaskFormDirty.value = false

    if (route.copyFrom) {
      const sourceTask = resolveTaskById(route.copyFrom)
      if (sourceTask) {
        cacheTask(sourceTask)
      }
      void loadCopyInitialData(route.copyFrom)
      return
    }

    formInitialData.value = undefined
    return
  }

  if (route.view === 'edit') {
    if (!route.taskId) {
      currentView.value = 'list'
      activeTaskId.value = ''
      formInitialData.value = undefined
      formErrorMessage.value = '未找到要编辑的任务'
      return
    }
    const task = resolveTaskById(route.taskId)
    if (task) {
      cacheTask(task)
    }
    void loadEditInitialData(route.taskId)
    return
  }

  const task = route.taskId ? resolveTaskById(route.taskId) : undefined
  currentView.value = 'detail'
  activeTaskId.value = task?.id || route.taskId || ''
  formInitialData.value = undefined
  formErrorMessage.value = task ? '' : '未找到任务详情，请返回列表重试'
}

const syncRouteFromHash = (): void => {
  const route = parseHashRoute()
  applyRoute(route)
  lastHash.value = window.location.hash || '#/outreach'
}

const navigate = (route: HashRoute): void => {
  const currentRoute = parseHashRoute()
  if (isSameRoute(currentRoute, route)) return

  if (hasUnsavedTaskFormChanges.value) {
    pendingLeaveRoute.value = route
    openLeaveConfirmDialog()
    return
  }

  commitNavigation(route)
}

const fetchTaskList = async (): Promise<void> => {
  const shopId = props.shopId?.trim() || ''
  if (!shopId) {
    taskList.value = []
    total.value = 0
    errorMessage.value = '缺少 shopId，无法加载任务列表'
    emptyMessage.value = '暂无建联任务，点击右上角新增任务'
    return
  }

  isLoading.value = true
  try {
    const apiStatus = statusQuery.value ? FILTER_UI_TO_API_STATUS[statusQuery.value] : undefined
    const result = await getOutreachTaskList(
      {
        page: page.value,
        pageSize: pageSize.value
      },
      {
        shopId,
        keyword: keywordQuery.value || undefined,
        status: apiStatus
      }
    )

    const normalized = result.list.map(normalizeTaskItem)
    const filtered = applyTaskFilters(normalized)
    taskList.value = filtered
    total.value = filtered.length
    errorMessage.value = ''
    emptyMessage.value = '暂无建联任务，点击右上角新增任务'
  } catch (error: any) {
    taskList.value = []
    total.value = 0
    errorMessage.value = error?.message || '任务列表加载失败'
    emptyMessage.value = '暂无建联任务，点击右上角新增任务'
  } finally {
    isLoading.value = false
  }
}

const fetchTaskFilterOptions = async (): Promise<void> => {
  const shopId = props.shopId?.trim() || ''
  if (!shopId) {
    taskFilterOptions.value = undefined
    return
  }

  try {
    const result = await getOutreachCreatorFilterItems(shopId)
    taskFilterOptions.value = buildTaskFilterOptions(result)
  } catch (_error) {
    taskFilterOptions.value = undefined
  }
}

const handleSearch = (): void => {
  keywordInput.value = sanitizeKeyword(keywordInput.value)
  keywordQuery.value = keywordInput.value
  statusQuery.value = statusInput.value
  const shouldFetchImmediately = page.value === 1
  page.value = 1
  if (shouldFetchImmediately) {
    void fetchTaskList()
  }
}

const changePage = (nextPage: number): void => {
  if (nextPage < 1 || nextPage > totalPages.value) return
  page.value = nextPage
}

const handlePageSizeChange = (): void => {
  page.value = 1
  void fetchTaskList()
}

const showActionMessage = (content: string, type: 'success' | 'error' | 'warning' | 'info' = 'info'): void => {
  message[type](content, {
    duration: 2200
  })
}

const openConfirmDialog = (title: string, content: string): Promise<boolean> => {
  return new Promise((resolve) => {
    let settled = false

    const settle = (value: boolean): void => {
      if (settled) return
      settled = true
      resolve(value)
    }

    dialog.warning({
      title,
      content,
      positiveText: '确定',
      negativeText: '取消',
      closable: false,
      maskClosable: false,
      positiveButtonProps: {
        color: '#0f67ff'
      },
      negativeButtonProps: {
        color: '#0f67ff',
        ghost: true
      },
      onPositiveClick: () => {
        settle(true)
      },
      onNegativeClick: () => {
        settle(false)
      },
      onClose: () => {
        settle(false)
      }
    })
  })
}

const isSameRoute = (first: HashRoute, second: HashRoute): boolean => {
  return buildHash(first) === buildHash(second)
}

const commitNavigation = (route: HashRoute): void => {
  const targetHash = buildHash(route)
  const currentHash = window.location.hash || '#/outreach'

  if (targetHash === currentHash) {
    applyRoute(route)
    lastHash.value = targetHash
    return
  }

  allowNextHashNavigationWithoutConfirm.value = true
  window.location.hash = targetHash
}

const openLeaveConfirmDialog = (): void => {
  if (isLeaveDialogOpen.value) return

  isLeaveDialogOpen.value = true

  void openConfirmDialog('放弃修改', '任务表单已发生变化，确认离开当前页面吗？').then((confirmed) => {
    isLeaveDialogOpen.value = false

    const targetRoute = pendingLeaveRoute.value
    pendingLeaveRoute.value = null

    if (!confirmed || !targetRoute) return

    commitNavigation(targetRoute)
  })
}

const goToTaskDetail = (task: OutreachTaskItem): void => {
  cacheTask(task)
  navigate({
    view: 'detail',
    taskId: task.id
  })
}

const handleTaskAction = async (task: OutreachTaskItem, action: TaskAction): Promise<void> => {
  cacheTask(task)

  if (action === 'view') {
    goToTaskDetail(task)
    return
  }

  if (action === 'edit') {
    navigate({ view: 'edit', taskId: task.id })
    return
  }

  if (action === 'copy') {
    navigate({ view: 'create', copyFrom: task.id })
    return
  }

  if (action === 'start') {
    const confirmed = await openConfirmDialog('启动任务', '确认启动本任务吗？')
    if (!confirmed) return

    try {
      const shopId = props.shopId?.trim() || ''
      if (!shopId) {
        showActionMessage('缺少 shopId，无法启动任务', 'error')
        return
      }
      const lastModificationTime = await getTaskLastModificationTime(task.id)
      await startOutreachTask(task.id, {
        lastModificationTime,
        shopId
      })
      showActionMessage('任务已进入启动队列', 'success')
      void fetchTaskList()
    } catch (error: any) {
      showActionMessage(error?.message || '启动任务失败', 'error')
    }
    return
  }

  const confirmed = await openConfirmDialog('结束任务', '要结束本任务吗？')
  if (!confirmed) return

  try {
    const shopId = props.shopId?.trim() || ''
    if (!shopId) {
      showActionMessage('缺少 shopId，无法结束任务', 'error')
      return
    }
    const lastModificationTime = await getTaskLastModificationTime(task.id)
    await stopOutreachTask(task.id, {
      lastModificationTime,
      shopId
    })
    showActionMessage('任务已结束', 'success')
    void fetchTaskList()
  } catch (error: any) {
    showActionMessage(error?.message || '结束任务失败', 'error')
  }
}

const goToCreateTaskInCurrentTab = (): void => {
  navigate({ view: 'create' })
}

const goBackToList = (): void => {
  navigate({ view: 'list' })
}

const handleDetailModalShowChange = (value: boolean): void => {
  if (!value && isTaskModalVisible.value) {
    goBackToList()
  }
}

const handleDetailEdit = (): void => {
  const task = activeTask.value
  if (!task) return

  if (task.status !== '未启动') {
    showActionMessage('仅未启动任务可编辑', 'warning')
    return
  }

  navigate({ view: 'edit', taskId: task.id })
}

const handleDetailEnd = async (): Promise<void> => {
  const task = activeTask.value
  if (!task) return

  if (task.status !== '运行中') {
    showActionMessage('仅运行中任务可结束', 'warning')
    return
  }

  const confirmed = await openConfirmDialog('结束任务', '确定要结束该任务吗？')
  if (!confirmed) return

  try {
    const shopId = props.shopId?.trim() || ''
    if (!shopId) {
      showActionMessage('缺少 shopId，无法结束任务', 'error')
      return
    }
    const lastModificationTime = await getTaskLastModificationTime(task.id)
    await stopOutreachTask(task.id, {
      lastModificationTime,
      shopId
    })
    showActionMessage('任务已结束', 'success')
    await fetchTaskList()
  } catch (error: any) {
    showActionMessage(error?.message || '结束任务失败', 'error')
  }
}

const onTaskFormSubmit = async (payload: CreateOutreachTaskFormPayload): Promise<void> => {
  const shopId = props.shopId?.trim() || ''
  isFormSubmitting.value = true
  formErrorMessage.value = ''

  try {
    if (!shopId) {
      formErrorMessage.value = '缺少 shopId，无法保存任务'
      return
    }

    if (currentView.value === 'edit' && activeTaskId.value) {
      const detailResult = await getOutreachTaskDetail(activeTaskId.value)
      const detailPayload = (detailResult?.data ?? detailResult ?? {}) as Record<string, any>
      const lastModificationTime = String(detailPayload.lastModificationTime || '').trim()
      await editOutreachTask(activeTaskId.value, toEditTaskApiPayload(activeTaskId.value, shopId, payload, lastModificationTime))
      taskFormCache.value[activeTaskId.value] = payload
      showActionMessage('任务已更新', 'success')
    } else {
      const createdTask = await createOutreachTask(toCreateTaskApiPayload(shopId, payload))
      if (createdTask?.id) {
        taskFormCache.value[String(createdTask.id)] = payload
      }
      showActionMessage('任务已创建', 'success')
    }

    isTaskFormDirty.value = false
    navigate({ view: 'list' })
    page.value = 1
    await fetchTaskList()
  } catch (error: any) {
    formErrorMessage.value = error?.message || '保存任务失败，请稍后重试'
  } finally {
    isFormSubmitting.value = false
  }
}

const onHashChange = (): void => {
  if (isRestoringHash.value) {
    isRestoringHash.value = false
    return
  }

  if (allowNextHashNavigationWithoutConfirm.value) {
    allowNextHashNavigationWithoutConfirm.value = false
    const route = parseHashRoute()
    applyRoute(route)
    lastHash.value = window.location.hash || '#/outreach'
    return
  }

  const incomingRoute = parseHashRoute()
  const incomingHash = window.location.hash || '#/outreach'

  if (hasUnsavedTaskFormChanges.value && incomingHash !== lastHash.value) {
    pendingLeaveRoute.value = incomingRoute
    isRestoringHash.value = true
    window.location.hash = lastHash.value
    openLeaveConfirmDialog()
    return
  }

  applyRoute(incomingRoute)
  lastHash.value = window.location.hash || '#/outreach'
}

const onBeforeUnload = (event: BeforeUnloadEvent): void => {
  if (!isTaskFormView.value || !isTaskFormDirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

onMounted(() => {
  keywordInput.value = sanitizeKeyword(keywordInput.value)
  keywordQuery.value = keywordInput.value
  statusQuery.value = statusInput.value
  durationTimer = window.setInterval(() => {
    durationNow.value = Date.now()
  }, 1000)

  syncRouteFromHash()
  void fetchTaskList()
  void fetchTaskFilterOptions()

  window.addEventListener('hashchange', onHashChange)
  window.addEventListener('beforeunload', onBeforeUnload)
})

onUnmounted(() => {
  if (durationTimer) {
    window.clearInterval(durationTimer)
    durationTimer = null
  }
  window.removeEventListener('hashchange', onHashChange)
  window.removeEventListener('beforeunload', onBeforeUnload)
})

watch([page, pageSize], () => {
  void fetchTaskList()
})

watch(
  () => props.shopId,
  () => {
    page.value = 1
    void fetchTaskList()
    void fetchTaskFilterOptions()
  }
)

watch(totalPages, (value) => {
  if (page.value > value) {
    page.value = value
  }
})
</script>

<template>
  <div class="task-page">
    <header class="page-header">
      <h1>一键建联-任务管理</h1>
      <button class="add-btn" type="button" @click="goToCreateTaskInCurrentTab">新增任务</button>
    </header>

    <section class="filter-panel">
      <div class="field-item">
        <label for="task-name">任务名称：</label>
        <input
          id="task-name"
          v-model="keywordInput"
          maxlength="20"
          placeholder="请输入关键词"
          type="text"
          @keydown.enter.prevent="handleSearch"
        />
      </div>
      <div class="field-item">
        <label for="task-status">任务状态：</label>
        <select id="task-status" v-model="statusInput">
          <option value="">全部</option>
          <option v-for="option in statusOptions.filter((item) => item)" :key="option" :value="option">{{ option }}</option>
        </select>
      </div>
      <button class="search-btn" type="button" @click="handleSearch">搜索</button>
    </section>

    <section class="table-panel">
      <div class="table-wrap">
        <table class="task-table">
          <thead>
            <tr>
              <th>序号</th>
              <th>任务名称</th>
              <th>启动时间</th>
              <th>建联进度</th>
              <th>运行时长</th>
              <th>任务状态</th>
              <th>任务管理</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="isLoading">
              <td class="empty-row" colspan="7">加载中...</td>
            </tr>
            <tr v-else-if="errorMessage">
              <td class="empty-row" colspan="7">{{ errorMessage }}</td>
            </tr>
            <tr v-else-if="taskList.length === 0">
              <td class="empty-row" colspan="7">{{ emptyMessage }}</td>
            </tr>
            <template v-else>
              <tr v-for="(item, index) in taskList" :key="item.id">
                <td>{{ getRowIndex(index) }}</td>
                <td>
                  <button class="name-link" type="button" @click="goToTaskDetail(item)">{{ item.taskName }}</button>
                </td>
                <td>{{ item.startTime }}</td>
                <td>
                  <button class="progress-link" type="button" @click="goToTaskDetail(item)">
                    {{ item.linkedCount }} / {{ item.planCount }}
                  </button>
                </td>
                <td>{{ getTaskDurationText(item) }}</td>
                <td>
                  <span :class="['status-pill', getStatusClass(item.status)]">{{ item.status }}</span>
                </td>
                <td>
                  <div class="icon-actions">
                    <button
                      v-for="action in getTaskActions(item.status)"
                      :key="action"
                      class="icon-action-btn"
                      :title="ACTION_META[action].title"
                      type="button"
                      @click="handleTaskAction(item, action)"
                    >
                      <span aria-hidden="true">{{ ACTION_META[action].icon }}</span>
                    </button>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <footer class="pagination-row">
        <span class="total-text">共 {{ total }} 条</span>
        <div class="pager">
          <label class="page-size-label">
            每页
            <select v-model.number="pageSize" @change="handlePageSizeChange">
              <option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }}</option>
            </select>
            条
          </label>
          <button :disabled="page <= 1" type="button" @click="changePage(page - 1)">上一页</button>
          <span class="page-index">{{ page }} / {{ totalPages }}</span>
          <button :disabled="page >= totalPages" type="button" @click="changePage(page + 1)">下一页</button>
        </div>
      </footer>
    </section>

    <NModal
      :show="isDetailModalVisible"
      :mask-closable="true"
      :close-on-esc="true"
      transform-origin="center"
      @update:show="handleDetailModalShowChange"
    >
      <NCard
        v-if="isDetailModalVisible"
        class="detail-modal-card"
        :bordered="false"
        role="dialog"
        title="查看任务"
      >
        <template #header-extra>
          <button class="detail-modal-close-btn" type="button" @click="goBackToList">×</button>
        </template>

        <OutreachTaskDetailView :task="activeTask" :task-id="activeTaskId" @edit="handleDetailEdit" @end="handleDetailEnd" />
      </NCard>
    </NModal>

    <CreateOutreachTaskModal
      v-if="isTaskFormModalVisible"
      :visible="isTaskFormModalVisible"
      mode="modal"
      :title="formTitle"
      :show-close="true"
      :initial-data="formInitialData"
      :filter-options="taskFilterOptions"
      :max-plan-count="maxPlanCount"
      :saving="isFormSubmitting"
      :submit-error="formErrorMessage"
      @submit="onTaskFormSubmit"
      @cancel="goBackToList"
      @dirty-change="(dirty) => (isTaskFormDirty = dirty)"
    />
  </div>
</template>

<style scoped>
.task-page {
  min-height: 100vh;
  padding: 24px;
  background: #f4f7fb;
}

.action-message {
  margin-bottom: 12px;
  border: 1px solid #cce2ff;
  border-radius: 8px;
  background: #eef5ff;
  color: #1f63d8;
  padding: 8px 10px;
  font-size: 13px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-header h1 {
  margin: 0;
  color: #1f2d3d;
  font-size: 22px;
  font-weight: 700;
}

.add-btn,
.search-btn {
  border: 0;
  border-radius: 8px;
  background: #0f67ff;
  color: #fff;
  padding: 9px 14px;
  font-size: 14px;
  cursor: pointer;
}

.filter-panel {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
  padding: 14px 16px;
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #fff;
  margin-bottom: 14px;
}

.field-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.field-item label {
  color: #3c4a5b;
  font-size: 14px;
}

.field-item input,
.field-item select {
  height: 34px;
  border: 1px solid #c9d3e2;
  border-radius: 6px;
  padding: 0 10px;
  min-width: 220px;
  font-size: 14px;
  color: #1f2d3d;
  background: #fff;
}

.table-panel,
.detail-panel {
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #fff;
}

.table-wrap {
  width: 100%;
  overflow-x: auto;
}

.task-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 920px;
}

.task-table th,
.task-table td {
  text-align: left;
  padding: 12px 14px;
  border-bottom: 1px solid #ecf1f7;
  font-size: 14px;
  color: #2b3a4a;
}

.task-table th {
  font-weight: 600;
  color: #4a5868;
  background: #f8fafc;
}

.name-link,
.progress-link {
  border: 0;
  background: transparent;
  color: #0f67ff;
  cursor: pointer;
  padding: 0;
  font-size: 14px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 18px;
}

.status-pill.is-running {
  background: #e8f3ff;
  color: #0f67ff;
}

.status-pill.is-pending {
  background: #f5f7fb;
  color: #607287;
}

.status-pill.is-ended {
  background: #fff1ef;
  color: #d4380d;
}

.status-pill.is-completed {
  background: #edf8f2;
  color: #1f8f50;
}

.icon-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.icon-action-btn {
  width: 28px;
  height: 28px;
  border: 1px solid #d0d9e6;
  border-radius: 6px;
  background: #fff;
  color: #2f4056;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

.icon-action-btn:hover {
  border-color: #0f67ff;
  color: #0f67ff;
  background: #eef5ff;
}

.empty-row {
  text-align: center !important;
  color: #7d8da1 !important;
}

.pagination-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
}

.total-text {
  color: #5b6a7a;
  font-size: 13px;
}

.pager {
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-size-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #5b6a7a;
}

.page-size-label select {
  height: 28px;
  border: 1px solid #d0d9e6;
  border-radius: 6px;
  padding: 0 8px;
}

.pager button {
  min-width: 64px;
  height: 30px;
  border: 1px solid #d0d9e6;
  border-radius: 6px;
  background: #fff;
  color: #2b3a4a;
  cursor: pointer;
  padding: 0 8px;
}

.pager button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.page-index {
  color: #5b6a7a;
  font-size: 13px;
}

.detail-panel {
  padding: 18px;
}

.detail-modal-card {
  width: 720px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 40px);
  border-radius: 12px;
  overflow: auto;
}

.detail-modal-close-btn {
  border: 0;
  background: transparent;
  color: #6b7b90;
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.detail-modal-close-btn:hover {
  color: #1f63d8;
}

.detail-panel h2 {
  margin: 0 0 14px;
  color: #213247;
  font-size: 20px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.detail-item {
  border: 1px solid #e6edf8;
  border-radius: 8px;
  background: #fafcff;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.detail-item span {
  font-size: 12px;
  color: #63758d;
}

.detail-item strong {
  font-size: 14px;
  color: #1f2d3d;
  font-weight: 600;
}

.empty-detail {
  color: #7d8da1;
}

@media (max-width: 900px) {
  .task-page {
    padding: 14px;
  }

  .page-header h1 {
    font-size: 18px;
  }

  .add-btn,
  .search-btn {
    padding: 8px 12px;
    font-size: 13px;
  }

  .field-item input,
  .field-item select {
    min-width: 180px;
  }

  .pagination-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .detail-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
