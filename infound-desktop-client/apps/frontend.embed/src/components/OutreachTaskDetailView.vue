<script setup lang="ts">
import { computed, h, onUnmounted, ref, watch } from 'vue'
import { NAlert, NAvatar, NButton, NCard, NDataTable, NDescriptions, NDescriptionsItem, NEllipsis, NIcon, NList, NListItem, NPagination, type DataTableColumns } from 'naive-ui'
import { getOutreachCreatorFilterItems, getOutreachTaskDetail, getOutreachTaskRecords } from '../api/outreach-task.api'
import type { CreateOutreachTaskFilterOptions, SelectOptionItem } from '../types/outreach-task-form'
import { formatDateTimeToLocal } from '../utils/date-time'
import { buildTaskFilterOptions } from '../utils/outreach-creator-filter-items'

type TaskStatus = '运行中' | '未启动' | '已结束' | '已完成' | '已取消'

interface TaskInfo {
  id: string
  taskName: string
  startTime: string
  planCount: number
  linkedCount: number
  status: TaskStatus
  raw?: Record<string, any>
}

interface RuntimeRow {
  id: string
  creatorName: string
  creatorAvatar: string
  followers: string
  gmv: string
  messageTime: string
}

interface MessageDetail {
  content: string
  productMessageEnabled: boolean
  productIds: string[]
}

interface TaskDetailData {
  taskName: string
  startTime: string
  status: TaskStatus
  progress: {
    linked: number
    total: number
  }
  filterSummary: string[]
  creatorSortLabel: string
  showCreatorSortSection: boolean
  outreachCreatorTypeLabel: string
  messageTemplate: {
    firstMessage: MessageDetail
    replyMessage?: MessageDetail
  }
  runtimeRows: RuntimeRow[]
}

const props = defineProps<{
  task: TaskInfo | null
  taskId?: string
  shopId?: string
  filterOptions?: CreateOutreachTaskFilterOptions
}>()

const emit = defineEmits<{
  (event: 'edit'): void
  (event: 'end'): void
}>()

const CREATOR_TYPE_LABEL_MAP: Record<string, string> = {
  ALL: '建联所有达人',
  NEW_ONLY: '只建联新达人',
  NEW_AND_NOT_REPLIED: '建联新达人和未回复达人'
}

const resolvedFilterOptions = ref<CreateOutreachTaskFilterOptions | undefined>(undefined)

const syncFilterOptionsFromProps = (): void => {
  if (props.filterOptions) {
    resolvedFilterOptions.value = props.filterOptions
    return
  }

  resolvedFilterOptions.value = undefined
}

const loadFilterOptions = async (): Promise<void> => {
  if (props.filterOptions) {
    resolvedFilterOptions.value = props.filterOptions
    return
  }

  const shopId = String(props.shopId || '').trim()
  if (!shopId) {
    resolvedFilterOptions.value = undefined
    return
  }

  try {
    const result = await getOutreachCreatorFilterItems(shopId)
    resolvedFilterOptions.value = buildTaskFilterOptions(result)
  } catch (_error) {
    resolvedFilterOptions.value = undefined
  }
}

watch(
  () => props.filterOptions,
  () => {
    syncFilterOptionsFromProps()
  },
  { immediate: true, deep: true }
)

watch(
  () => String(props.shopId ?? '').trim(),
  (newShopId, oldShopId) => {
    if (oldShopId !== undefined && newShopId === oldShopId) return
    void loadFilterOptions()
  },
  { immediate: true }
)

const isLoading = ref(false)
const errorMessage = ref('')
const detail = ref<TaskDetailData | null>(null)
const runtimeRows = ref<RuntimeRow[]>([])
const runtimeTotal = ref(0)
const isRuntimeLoading = ref(false)
const isRuntimePolling = ref(false)
const isDetailPolling = ref(false)
const runtimePage = ref(1)
const runtimePageSize = ref(10)
const runtimePageSizeOptions = [10, 20, 50]
let detailPollTimer: ReturnType<typeof window.setInterval> | null = null

const runtimeTotalPages = computed(() => {
  return Math.max(1, Math.ceil(runtimeTotal.value / runtimePageSize.value))
})
const runtimeTableEmptyText = computed(() => (isRuntimeLoading.value ? '' : '暂无数据'))

const pagedRuntimeRows = computed(() => runtimeRows.value)
const currentTaskId = computed(() => String(props.taskId || props.task?.id || '').trim())
const shouldPollTaskDetail = computed(() => {
  const currentStatus = detail.value?.status || props.task?.status
  return Boolean(currentTaskId.value) && currentStatus === '运行中'
})

const canEdit = computed(() => detail.value?.status === '未启动')
const canEnd = computed(() => detail.value?.status === '运行中')
const getCreatorAvatarSrc = (avatar: string): string | undefined => {
  const normalizedAvatar = String(avatar || '').trim()
  if (!normalizedAvatar) return undefined
  const lowerCaseAvatar = normalizedAvatar.toLowerCase()
  if (lowerCaseAvatar === 'null' || lowerCaseAvatar === 'undefined') return undefined
  return normalizedAvatar
}

const renderDefaultCreatorAvatarIcon = () =>
  h(
    NIcon,
    {
      size: 16,
      style: {
        color: '#97a3b4'
      }
    },
    {
      default: () =>
        h(
          'svg',
          {
            xmlns: 'http://www.w3.org/2000/svg',
            viewBox: '0 0 24 24',
            fill: 'none',
            stroke: 'currentColor',
            'stroke-width': '2',
            'stroke-linecap': 'round',
            'stroke-linejoin': 'round'
          },
          [
            h('path', { d: 'M20 21a8 8 0 0 0-16 0' }),
            h('circle', { cx: '12', cy: '7', r: '4' })
          ]
        )
    }
  )
const runtimeTableColumns: DataTableColumns<RuntimeRow> = [
  {
    title: '达人',
    key: 'creator',
    render: (row) => {
      const avatarSrc = getCreatorAvatarSrc(row.creatorAvatar)
      const avatarNode = avatarSrc
        ? h(NAvatar, {
            round: true,
            size: 28,
            src: avatarSrc,
            class: 'creator-avatar',
            style: {
              width: '28px',
              height: '28px',
              minWidth: '28px',
              flexShrink: 0
            }
          })
        : h(
            NAvatar,
            {
              round: true,
              size: 28,
              class: 'creator-avatar',
              style: {
                width: '28px',
                height: '28px',
                minWidth: '28px',
                flexShrink: 0
              }
            },
            {
              default: () => renderDefaultCreatorAvatarIcon()
            }
          )

      return h(
        'div',
        {
          class: 'creator-cell',
          style: {
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            minHeight: '32px',
            width: '100%',
            minWidth: 0
          }
        },
        [
          avatarNode,
          h(
            'div',
            {
              class: 'creator-name-wrap',
              style: {
                display: 'flex',
                alignItems: 'center',
                minWidth: 0,
                flex: 1,
                minHeight: '28px'
              }
            },
            [
              h(
                NEllipsis,
                {
                  class: 'creator-name',
                  tooltip: true,
                  lineClamp: 1,
                  style: {
                    display: 'flex',
                    alignItems: 'center',
                    width: '100%',
                    minHeight: '28px'
                  }
                },
                { default: () => row.creatorName }
              )
            ]
          )
        ]
      )
    }
  },
  {
    title: '粉丝数量',
    key: 'followers'
  },
  {
    title: 'GMV',
    key: 'gmv'
  },
  {
    title: '消息发送时间',
    key: 'messageTime',
    width: 180
  }
]

const toNumber = (value: unknown, fallback: number = 0): number => {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : fallback
}

const normalizeStatusToUI = (value: unknown): TaskStatus => {
  const source = String(value || '').trim()
  const normalized = source.toUpperCase()

  if (normalized === 'RUNNING' || source === '运行中') return '运行中'
  if (normalized === 'PENDING' || normalized === 'NOT_STARTED' || source === '未启动') return '未启动'
  if (normalized === 'COMPLETED' || source === '已完成') return '已完成'
  if (normalized === 'ENDED' || normalized === 'STOPPED' || source === '已结束') return '已结束'
  if (normalized === 'CANCELED' || normalized === 'CANCELLED' || source === '已取消') return '已取消'

  return '未启动'
}

const normalizeOptionKey = (value: string): string => String(value || '').replace(/\s+/g, '').toLowerCase()

const buildOptionLabelLookup = <T extends string | number>(options: Array<SelectOptionItem<T>> | undefined): Map<string, string> => {
  const map = new Map<string, string>()
  if (!Array.isArray(options)) return map

  options.forEach((option, index) => {
    const label = String(option?.label ?? '').trim()
    if (!label) return

    map.set(normalizeOptionKey(String(option.value)), label)
    map.set(String(index), label)
  })

  return map
}

const resolveOptionLabel = <T extends string | number>(
  value: unknown,
  options: Array<SelectOptionItem<T>> | undefined,
  fallback: string = ''
): string => {
  const map = buildOptionLabelLookup(options)
  const rawText = String(value ?? '').trim()
  if (!rawText) return fallback

  const direct = map.get(normalizeOptionKey(rawText))
  if (direct) return direct

  const asNumber = Number(rawText)
  if (Number.isInteger(asNumber) && asNumber >= 0) {
    const indexed = map.get(String(asNumber))
    if (indexed) return indexed
  }

  return rawText || fallback
}

const formatMultiSelectLabels = <T extends string | number>(
  value: unknown,
  options: Array<SelectOptionItem<T>> | undefined
): string => {
  const map = buildOptionLabelLookup(options)
  const tokens = Array.isArray(value)
    ? value.map((item) => String(item).trim()).filter(Boolean)
    : String(value || '')
        .split(/[\s,，]+/)
        .map((item) => item.trim())
        .filter(Boolean)

  if (tokens.length === 0) return '（空）'

  const labels = tokens
    .map((token) => map.get(normalizeOptionKey(token)) || token)
    .filter(Boolean)

  return labels.join(', ') || '（空）'
}

const buildDefaultMessageTemplate = (): TaskDetailData['messageTemplate'] => {
  return {
    firstMessage: {
      content: '您好，我们关注到您的内容风格与店铺商品匹配，想邀请您参与合作推广。',
      productMessageEnabled: true,
      productIds: ['100001', '100002']
    },
    replyMessage: {
      content: '感谢回复，合作细节如下：佣金比例可协商，支持寄样与快速排期。',
      productMessageEnabled: false,
      productIds: []
    }
  }
}

const normalizeProductIds = (value: unknown): string[] => {
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean)
  }

  if (typeof value === 'string') {
    return value
      .split(/[\s,，]+/)
      .map((item) => item.trim())
      .filter(Boolean)
  }

  return []
}

const normalizeProductCategoryLabels = (value: unknown, options: Array<SelectOptionItem<string>> | undefined): string => {
  return formatMultiSelectLabels(value, options)
}

const getFirstValidText = (...values: unknown[]): string => {
  for (const value of values) {
    const text = String(value ?? '').trim()
    if (!text) continue
    if (text.toLowerCase() === 'null' || text.toLowerCase() === 'undefined') continue
    return text
  }
  return ''
}

const normalizeRuntimeRows = (rawList: unknown, taskId: string): RuntimeRow[] => {
  if (!Array.isArray(rawList) || rawList.length === 0) {
    return []
  }

  return rawList.map((item: any, index: number) => ({
    id: String(item?.id ?? item?.platformCreatorId ?? item?.creatorId ?? `${taskId}-runtime-${index + 1}`),
    creatorName:
      getFirstValidText(
        item?.platformCreatorDisplayName,
        item?.platformCreatorUsername
      ) || '-',
    creatorAvatar: getFirstValidText(item?.avatar),
    followers: String(item?.followers ?? item?.fansCount ?? item?.followerCount ?? '-'),
    gmv: String(item?.gmv ?? item?.gmvRange ?? '-'),
    messageTime: formatDateTimeToLocal(item?.sendTime ?? item?.messageTime ?? item?.sentAt ?? item?.createdAt ?? '-')
  }))
}

const buildDetailFromSource = (source: Record<string, any>, fallbackTask?: TaskInfo | null): TaskDetailData => {
  const filterConfig = source.filterConfig || {}
  const creatorFilter = source.creatorFilter || {}
  const creatorFilters = filterConfig.creatorFilters || {}
  const followerFilters = filterConfig.followerFilters || {}
  const performanceFilters = filterConfig.performanceFilters || {}
  const filterOptions = resolvedFilterOptions.value
  const searchKeyword = String(filterConfig.searchKeyword ?? creatorFilter.keyword ?? '').trim()

  const productCategories = Array.isArray(creatorFilters.productCategorySelections)
    ? normalizeProductCategoryLabels(creatorFilters.productCategorySelections, filterOptions?.productCategoryOptions)
    : normalizeProductCategoryLabels(creatorFilter.productCategories, filterOptions?.productCategoryOptions)

  const avgCommissionRateLabel = resolveOptionLabel(
    creatorFilter.avgCommissionRate ?? creatorFilters.avgCommissionRate,
    filterOptions?.avgCommissionRateOptions,
    'All'
  )
  const contentTypeLabel = resolveOptionLabel(
    creatorFilter.contentTypes ?? creatorFilters.contentType,
    filterOptions?.contentTypeOptions,
    'All'
  )
  const creatorAgencyLabel = resolveOptionLabel(
    creatorFilter.creatorAgency ?? creatorFilters.creatorAgency,
    filterOptions?.creatorAgencyOptions,
    'All'
  )
  const fansGenderLabel = resolveOptionLabel(
    creatorFilter.fansGender ?? followerFilters.followerGender,
    filterOptions?.followerGenderOptions,
    'All'
  )
  const fansAgeRange = Array.isArray(creatorFilter.fansAgeRange)
    ? formatMultiSelectLabels(creatorFilter.fansAgeRange, filterOptions?.followerAgeOptions)
    : Array.isArray(followerFilters.followerAgeSelections)
      ? formatMultiSelectLabels(followerFilters.followerAgeSelections, filterOptions?.followerAgeOptions)
      : '（空）'
  const gmvRange = Array.isArray(creatorFilter.gmvRange)
    ? formatMultiSelectLabels(creatorFilter.gmvRange, filterOptions?.gmvOptions)
    : Array.isArray(performanceFilters.gmvSelections)
      ? formatMultiSelectLabels(performanceFilters.gmvSelections, filterOptions?.gmvOptions)
      : '（空）'
  const salesCountRange = Array.isArray(creatorFilter.salesCountRange)
    ? formatMultiSelectLabels(creatorFilter.salesCountRange, filterOptions?.itemsSoldOptions)
    : Array.isArray(performanceFilters.itemsSoldSelections)
      ? formatMultiSelectLabels(performanceFilters.itemsSoldSelections, filterOptions?.itemsSoldOptions)
      : '（空）'
  const coBranding = Array.isArray(creatorFilter.coBranding) ? creatorFilter.coBranding.join(', ') : ''
  const fansCountMin = String(followerFilters.followerCountMin ?? creatorFilter.fansCountRange?.min ?? '0')
  const fansCountMax = String(followerFilters.followerCountMax ?? creatorFilter.fansCountRange?.max ?? '10,000,000+')

  const averageViewsPerVideoMin = String(creatorFilter.minAvgVideoViews ?? performanceFilters.averageViewsPerVideoMin ?? '0')
  const averageViewersPerLiveMin = String(creatorFilter.minAvgLiveViews ?? performanceFilters.averageViewersPerLiveMin ?? '0')
  const engagementRateMinPercent = String(creatorFilter.minEngagementRate ?? performanceFilters.engagementRateMinPercent ?? '0')

  const averageViewsPerVideoLabel = resolveOptionLabel(
    averageViewsPerVideoMin,
    filterOptions?.avgVideoViewsPresetOptions,
    averageViewsPerVideoMin
  )
  const averageViewersPerLiveLabel = resolveOptionLabel(
    averageViewersPerLiveMin,
    filterOptions?.avgLiveViewsPresetOptions,
    averageViewersPerLiveMin
  )
  const engagementRateLabel = resolveOptionLabel(
    engagementRateMinPercent,
    filterOptions?.engagementRatePresetOptions,
    engagementRateMinPercent
  )

  const creatorEstimatedPublishRateLabel = resolveOptionLabel(
    creatorFilter.creatorEstimatedPublishRate ?? performanceFilters.estPostRate,
    filterOptions?.estPostRateOptions,
    '（空）'
  )

  const filterSummary: string[] = []
  if (filterOptions?.showSearchKeywordFilter) {
    filterSummary.push(`关键词：${searchKeyword || '（空）'}`)
  }
  if (filterOptions?.productCategoryOptions?.length) {
    filterSummary.push(`商品类目：${productCategories}`)
  }
  if (filterOptions?.avgCommissionRateOptions?.length) {
    filterSummary.push(`平均佣金率：${avgCommissionRateLabel}`)
  }
  if (filterOptions?.contentTypeOptions?.length) {
    filterSummary.push(`内容类型：${contentTypeLabel}`)
  }
  if (filterOptions?.creatorAgencyOptions?.length) {
    filterSummary.push(`达人机构：${creatorAgencyLabel}`)
  }
  if (filterOptions?.fastGrowingOptions?.length) {
    filterSummary.push(`快速成长榜：${Boolean(creatorFilter.fastGrowing) ? '是' : '否'}`)
  }
  if (filterOptions?.notInvitedInPast90DaysOptions?.length) {
    filterSummary.push(`过去 90 天内未获邀请的达人：${Boolean(creatorFilter.notInvitedInPast90Days) ? '是' : '否'}`)
  }
  if (filterOptions?.followerAgeOptions?.length) {
    filterSummary.push(`粉丝年龄：${fansAgeRange}`)
  }
  if (filterOptions?.followerGenderOptions?.length) {
    filterSummary.push(`粉丝性别：${fansGenderLabel}`)
  }
  if (filterOptions?.followerCountPresetOptions?.length) {
    filterSummary.push(`粉丝数：${fansCountMin} - ${fansCountMax}`)
  }
  if (filterOptions?.gmvOptions?.length) {
    filterSummary.push(`GMV：${gmvRange}`)
  }
  if (filterOptions?.itemsSoldOptions?.length) {
    filterSummary.push(`成交件数：${salesCountRange}`)
  }
  if (filterOptions?.avgVideoViewsPresetOptions?.length) {
    filterSummary.push(`平均每个视频的播放量：${averageViewsPerVideoLabel}`)
  }
  if (filterOptions?.avgLiveViewsPresetOptions?.length) {
    filterSummary.push(`平均每场直播的观看人数：${averageViewersPerLiveLabel}`)
  }
  if (filterOptions?.engagementRatePresetOptions?.length) {
    filterSummary.push(`互动率 (%)：${engagementRateLabel}`)
  }
  if (filterOptions?.estPostRateOptions?.length) {
    filterSummary.push(`预计发布率：${creatorEstimatedPublishRateLabel}`)
  }
  if (filterOptions?.showBrandCollaborationFilter) {
    filterSummary.push(`品牌合作：${coBranding || '（空）'}`)
  }

  const showCreatorSortSection = Boolean(filterOptions?.sortOptions?.length)

  const sourceMessageTemplate =
    source.messageTemplate || {
      firstMessage: {
        content: source.firstMessage,
        productMessageEnabled: Boolean(source.attachProducts),
        productIds: normalizeProductIds(source.productIds)
      },
      replyMessage: source.replyMessage
        ? {
            content: source.replyMessage,
            productMessageEnabled: Boolean(source.attachProducts),
            productIds: normalizeProductIds(source.productIds)
          }
        : undefined
    }
  const firstMessageRaw = sourceMessageTemplate.firstMessage
  const replyMessageRaw = sourceMessageTemplate.replyMessage

  const defaultMessageTemplate = buildDefaultMessageTemplate()
  const firstMessage: MessageDetail = {
    content: String(firstMessageRaw?.content || defaultMessageTemplate.firstMessage.content),
    productMessageEnabled: Boolean(
      typeof firstMessageRaw?.productMessageEnabled === 'boolean'
        ? firstMessageRaw.productMessageEnabled
        : defaultMessageTemplate.firstMessage.productMessageEnabled
    ),
    productIds: Array.isArray(firstMessageRaw?.productIds)
      ? firstMessageRaw.productIds.map((item: any) => String(item)).filter(Boolean)
      : [...defaultMessageTemplate.firstMessage.productIds]
  }

  const creatorType = String(source.outreachCreatorType || source.outreachMode || 'ALL')
  const replyMessage =
    creatorType === 'ALL'
      ? {
          content: String(replyMessageRaw?.content || defaultMessageTemplate.replyMessage?.content || ''),
          productMessageEnabled: Boolean(
            typeof replyMessageRaw?.productMessageEnabled === 'boolean'
              ? replyMessageRaw.productMessageEnabled
              : defaultMessageTemplate.replyMessage?.productMessageEnabled
          ),
          productIds: Array.isArray(replyMessageRaw?.productIds)
            ? replyMessageRaw.productIds.map((item: any) => String(item)).filter(Boolean)
            : [...(defaultMessageTemplate.replyMessage?.productIds || [])]
        }
      : undefined

  return {
    taskName: String(source.taskName || fallbackTask?.taskName || '建联任务'),
    startTime: formatDateTimeToLocal(source.startTime || fallbackTask?.startTime || '-'),
    status: normalizeStatusToUI(source.status || fallbackTask?.status),
    progress: {
      linked: toNumber(source.linkedCount ?? source.realCount ?? source.completedCount ?? fallbackTask?.linkedCount, 0),
      total: toNumber(source.planCount ?? source.plannedCount ?? fallbackTask?.planCount, 0)
    },
    filterSummary,
    creatorSortLabel: showCreatorSortSection
      ? resolveOptionLabel(
          source.creatorSort ?? source.creatorFilter?.sortBy,
          filterOptions?.sortOptions,
          String(source.creatorSort ?? source.creatorFilter?.sortBy ?? '')
        )
      : '',
    showCreatorSortSection,
    outreachCreatorTypeLabel: CREATOR_TYPE_LABEL_MAP[creatorType] || creatorType || '建联所有达人',
    messageTemplate: {
      firstMessage,
      replyMessage
    },
    runtimeRows: []
  }
}

const lastDetailSource = ref<{ source: Record<string, any>; fallbackTask: TaskInfo | null } | null>(null)

const applyFilterLabelsToDetail = (): void => {
  if (!detail.value || !lastDetailSource.value) return
  const next = buildDetailFromSource(lastDetailSource.value.source, lastDetailSource.value.fallbackTask)
  detail.value = {
    ...detail.value,
    filterSummary: next.filterSummary,
    creatorSortLabel: next.creatorSortLabel,
    showCreatorSortSection: next.showCreatorSortSection,
    outreachCreatorTypeLabel: next.outreachCreatorTypeLabel
  }
}

const buildDetailFromTask = (task: TaskInfo): TaskDetailData => {
  return buildDetailFromSource(task.raw || {}, task)
}

const fetchRuntimeRows = async (options?: { silent?: boolean }): Promise<void> => {
  const silent = Boolean(options?.silent)
  const taskId = currentTaskId.value
  if (!taskId) {
    runtimeRows.value = []
    runtimeTotal.value = 0
    return
  }

  if (silent) {
    if (isRuntimePolling.value) return
    isRuntimePolling.value = true
  } else {
    isRuntimeLoading.value = true
  }

  try {
    const result = await getOutreachTaskRecords(taskId, {
      page: runtimePage.value,
      pageSize: runtimePageSize.value
    })
    runtimeRows.value = normalizeRuntimeRows(result.list, taskId)
    runtimeTotal.value = Number(result.total || 0)
  } catch (_error) {
    if (!silent) {
      runtimeRows.value = []
      runtimeTotal.value = 0
    }
  } finally {
    if (silent) {
      isRuntimePolling.value = false
    } else {
      isRuntimeLoading.value = false
    }
  }
}

const fetchTaskDetail = async (options?: { silent?: boolean }): Promise<void> => {
  const silent = Boolean(options?.silent)
  const taskId = currentTaskId.value
  if (!taskId && !props.task) {
    detail.value = null
    lastDetailSource.value = null
    errorMessage.value = '未找到任务详情，请返回列表后重试'
    runtimeRows.value = []
    runtimeTotal.value = 0
    return
  }

  if (silent) {
    if (isDetailPolling.value) return
    isDetailPolling.value = true
  } else {
    isLoading.value = true
    errorMessage.value = ''
  }

  try {
    if (taskId) {
      const result = await getOutreachTaskDetail(taskId)
      const payload = (result?.data ?? result ?? {}) as Record<string, any>
      lastDetailSource.value = { source: payload, fallbackTask: props.task }
      detail.value = buildDetailFromSource(payload, props.task)
      applyFilterLabelsToDetail()
    } else if (props.task) {
      lastDetailSource.value = { source: props.task.raw || {}, fallbackTask: props.task }
      detail.value = buildDetailFromTask(props.task)
      applyFilterLabelsToDetail()
    } else {
      detail.value = null
      lastDetailSource.value = null
      errorMessage.value = '未找到任务详情，请返回列表后重试'
    }
  } catch (_error) {
    if (silent) {
      return
    }
    if (props.task) {
      lastDetailSource.value = { source: props.task.raw || {}, fallbackTask: props.task }
      detail.value = buildDetailFromTask(props.task)
      applyFilterLabelsToDetail()
      errorMessage.value = ''
    } else {
      detail.value = null
      lastDetailSource.value = null
      errorMessage.value = '加载任务详情失败'
    }
  } finally {
    if (silent) {
      isDetailPolling.value = false
    } else {
      isLoading.value = false
    }
  }
}

const stopDetailPolling = (): void => {
  if (!detailPollTimer) return
  window.clearInterval(detailPollTimer)
  detailPollTimer = null
}

const startDetailPolling = (): void => {
  if (detailPollTimer) return
  detailPollTimer = window.setInterval(() => {
    if (!shouldPollTaskDetail.value) return
    void fetchTaskDetail({ silent: true })
    void fetchRuntimeRows({ silent: true })
  }, 3000)
}

const changeRuntimePage = (nextPage: number): void => {
  if (nextPage < 1 || nextPage > runtimeTotalPages.value) return
  runtimePage.value = nextPage
}

const handleRuntimePageSizeChange = (nextPageSize: number): void => {
  runtimePageSize.value = nextPageSize
  runtimePage.value = 1
}

watch(
  resolvedFilterOptions,
  () => {
    applyFilterLabelsToDetail()
  },
  { deep: true }
)

watch(
  currentTaskId,
  () => {
    runtimePage.value = 1
    void fetchTaskDetail()
    void fetchRuntimeRows()
  },
  { immediate: true }
)

watch([runtimePage, runtimePageSize], () => {
  if (!currentTaskId.value) return
  void fetchRuntimeRows()
})

watch(runtimeTotalPages, (value) => {
  if (runtimePage.value > value) {
    runtimePage.value = value
  }
})

watch(
  shouldPollTaskDetail,
  (value) => {
    if (value) {
      startDetailPolling()
      return
    }
    stopDetailPolling()
  },
  { immediate: true }
)

onUnmounted(() => {
  stopDetailPolling()
})
</script>

<template>
  <section class="detail-shell">
    <NAlert v-if="isLoading" class="detail-alert" type="info" :show-icon="false">加载详情中...</NAlert>
    <NAlert v-else-if="errorMessage" class="detail-alert" type="error" :show-icon="false">{{ errorMessage }}</NAlert>
    <template v-else-if="detail">
      <header class="detail-header">
        <h2>{{ detail.taskName }}</h2>
        <div class="header-actions">
          <NButton
            v-if="canEdit"
            size="small"
            tertiary
            @click="emit('edit')"
          >
            <span>编辑</span>
          </NButton>
          <NButton
            v-if="canEnd"
            size="small"
            tertiary
            type="error"
            @click="emit('end')"
          >
            <span>结束</span>
          </NButton>
        </div>
      </header>

      <NCard class="detail-section-card" :bordered="false" size="small" title="任务信息">
        <NDescriptions label-placement="left" :column="2" size="small">
          <NDescriptionsItem label="启动时间">{{ detail.startTime }}</NDescriptionsItem>
          <NDescriptionsItem label="建联状态">{{ detail.status }}</NDescriptionsItem>
          <NDescriptionsItem label="建联进度" :span="2">{{ detail.progress.linked }} / {{ detail.progress.total }}</NDescriptionsItem>
        </NDescriptions>
      </NCard>

      <NCard v-if="detail.filterSummary.length" class="detail-section-card" :bordered="false" size="small" title="筛选达人">
        <NList class="summary-list" :bordered="false" hoverable>
          <NListItem v-for="(item, index) in detail.filterSummary" :key="index" class="summary-list-item">
            {{ item }}
          </NListItem>
        </NList>
      </NCard>

      <NCard v-if="detail.showCreatorSortSection" class="detail-section-card" :bordered="false" size="small" title="达人排序">
        <NDescriptions label-placement="left" :column="1" size="small">
          <NDescriptionsItem label="排序方式">{{ detail.creatorSortLabel }}</NDescriptionsItem>
        </NDescriptions>
      </NCard>

      <NCard class="detail-section-card" :bordered="false" size="small" title="消息模板">
        <NDescriptions label-placement="left" :column="1" size="small">
          <NDescriptionsItem label="建联达人">{{ detail.outreachCreatorTypeLabel }}</NDescriptionsItem>
        </NDescriptions>

        <NCard class="message-card" size="small" embedded :bordered="false">
          <h4>首次消息</h4>
          <p>{{ detail.messageTemplate.firstMessage.content }}</p>
          <p class="message-meta">
            商品消息：{{ detail.messageTemplate.firstMessage.productMessageEnabled ? '已开启' : '未开启' }}
            <template v-if="detail.messageTemplate.firstMessage.productMessageEnabled">
              （商品ID：{{ detail.messageTemplate.firstMessage.productIds.join('、') || '无' }}）
            </template>
          </p>
        </NCard>

        <NCard v-if="detail.messageTemplate.replyMessage" class="message-card" size="small" embedded :bordered="false">
          <h4>回复达人消息</h4>
          <p>{{ detail.messageTemplate.replyMessage.content }}</p>
          <p class="message-meta">
            商品消息：{{ detail.messageTemplate.replyMessage.productMessageEnabled ? '已开启' : '未开启' }}
            <template v-if="detail.messageTemplate.replyMessage.productMessageEnabled">
              （商品ID：{{ detail.messageTemplate.replyMessage.productIds.join('、') || '无' }}）
            </template>
          </p>
        </NCard>
      </NCard>

      <NCard class="detail-section-card runtime-section-card" :bordered="false" size="small" title="任务运行情况">
        <div class="table-wrap">
          <NDataTable
            class="runtime-data-table"
            :columns="runtimeTableColumns"
            :data="isRuntimeLoading ? [] : pagedRuntimeRows"
            :loading="isRuntimeLoading"
            :bordered="false"
            :single-line="false"
            :row-key="(row) => row.id"
          >
            <template #empty>
              <div class="table-empty">{{ runtimeTableEmptyText }}</div>
            </template>
          </NDataTable>
        </div>

        <footer class="pagination-row">
          <span class="total-text">共 {{ runtimeTotal }} 条</span>
          <NPagination
            :page="runtimePage"
            :page-size="runtimePageSize"
            :item-count="runtimeTotal"
            :page-sizes="runtimePageSizeOptions"
            show-size-picker
            @update:page="changeRuntimePage"
            @update:page-size="handleRuntimePageSizeChange"
          />
        </footer>
      </NCard>
    </template>
  </section>
</template>

<style scoped>
.detail-shell {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-alert {
  border-radius: 10px;
}

.detail-header,
.detail-section-card {
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #fff;
  padding: 14px;
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.detail-header h2 {
  margin: 0;
  color: #1f2d3d;
  font-size: 20px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-section-card {
  --n-border-radius: 10px;
  padding: 0;
  overflow: hidden;
}

.detail-section-card:deep(.n-card-header) {
  padding: 14px 14px 0;
  border-bottom: none !important;
  box-shadow: none !important;
}

.detail-section-card:deep(.n-card-header__main) {
  color: #1f2d3d;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.2;
}

.detail-section-card:deep(.n-card__content) {
  padding: 12px 14px 14px;
  border-top: none !important;
  box-shadow: none !important;
}

.detail-section-card :deep(.n-descriptions) {
  color: #334155;
}

.detail-section-card :deep(.n-descriptions-table-header),
.detail-section-card :deep(.n-descriptions-table-content) {
  font-size: 14px;
}

.summary-list {
  color: #334155;
  font-size: 14px;
}

.summary-list-item {
  padding: 8px 0;
}

.message-card {
  border: 1px solid #e5ecf8;
  border-radius: 8px;
  background: #fafcff;
  padding: 10px 12px;
  margin-top: 10px;
}

.message-card h4 {
  margin: 0 0 8px;
  color: #1f2d3d;
  font-size: 14px;
}

.message-card p {
  margin: 0;
  color: #334155;
  font-size: 13px;
  line-height: 1.6;
}

.message-meta {
  margin-top: 6px !important;
  color: #5b6d83 !important;
  font-size: 12px !important;
}

.table-wrap {
  width: 100%;
  overflow-x: auto;
}

.creator-cell {
  width: 100%;
  min-width: 0;
}

.creator-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #97a3b4;
}

.creator-name-wrap {
  display: flex;
  align-items: center;
  min-width: 0;
  min-height: 28px;
}

.creator-name {
  display: flex;
  align-items: center;
  min-height: 28px;
  line-height: 1.2;
}

.runtime-data-table:deep(.n-data-table-th) {
  background: #f8fafc;
  color: #4b5c71;
  font-weight: 600;
}

.runtime-data-table:deep(.n-data-table-td) {
  color: #334155;
  vertical-align: middle;
}

.table-empty {
  padding: 24px 12px;
  text-align: center;
  color: #6b7f95;
}

.pagination-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-top: 10px;
}

.total-text {
  color: #5b6a7a;
  font-size: 13px;
}

.pagination-row :deep(.n-pagination) {
  margin-left: auto;
}

@media (max-width: 900px) {
  .detail-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .pagination-row {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
