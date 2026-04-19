<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { NAlert, NButton, NCard, NDataTable, NDescriptions, NDescriptionsItem, NList, NListItem, NPagination, type DataTableColumns } from 'naive-ui'
import { getOutreachTaskDetail, getOutreachTaskRecords } from '../api/outreach-task.api'
import {
  OUTREACH_AVG_COMMISSION_RATE_OPTIONS,
  OUTREACH_AVG_COMMISSION_RATE_LABEL_MAP,
  OUTREACH_CONTENT_TYPE_OPTIONS,
  OUTREACH_CONTENT_TYPE_LABEL_MAP,
  OUTREACH_CREATOR_AGENCY_OPTIONS,
  OUTREACH_CREATOR_AGENCY_LABEL_MAP,
  OUTREACH_CREATOR_TYPE_LABEL_MAP,
  OUTREACH_FOLLOWER_GENDER_OPTIONS,
  OUTREACH_FOLLOWER_GENDER_LABEL_MAP,
  OUTREACH_PRODUCT_CATEGORY_LABEL_MAP,
  OUTREACH_SORT_LABEL_MAP
} from '../constants/outreach-task-display'

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
  followers: string
  gmv: string
  outreachTask: string
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
}>()

const emit = defineEmits<{
  (event: 'edit'): void
  (event: 'end'): void
}>()

const PRODUCT_CATEGORY_LABEL_MAP = OUTREACH_PRODUCT_CATEGORY_LABEL_MAP
const AVG_COMMISSION_RATE_LABELS = OUTREACH_AVG_COMMISSION_RATE_OPTIONS
const CONTENT_TYPE_LABELS = OUTREACH_CONTENT_TYPE_OPTIONS
const CREATOR_AGENCY_LABELS = OUTREACH_CREATOR_AGENCY_OPTIONS
const FOLLOWER_GENDER_LABELS = OUTREACH_FOLLOWER_GENDER_OPTIONS
const SORT_LABEL_MAP = OUTREACH_SORT_LABEL_MAP

const isLoading = ref(false)
const errorMessage = ref('')
const detail = ref<TaskDetailData | null>(null)
const runtimeRows = ref<RuntimeRow[]>([])
const runtimeTotal = ref(0)
const isRuntimeLoading = ref(false)
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
const runtimeTableColumns: DataTableColumns<RuntimeRow> = [
  {
    title: '达人',
    key: 'creatorName',
    minWidth: 160
  },
  {
    title: '粉丝数量',
    key: 'followers',
    width: 120
  },
  {
    title: 'GMV',
    key: 'gmv',
    width: 120
  },
  {
    title: '建联任务',
    key: 'outreachTask',
    minWidth: 160
  },
  {
    title: '消息发送时间',
    key: 'messageTime',
    minWidth: 180
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

const getIndexedLabel = (value: unknown, labels: string[], fallback: string): string => {
  const index = Number(value)
  if (Number.isInteger(index) && index >= 0 && index < labels.length) {
    return labels[index] || fallback
  }
  const text = String(value ?? '').trim()
  return text || fallback
}

const getMappedLabel = (
  value: unknown,
  labels: string[],
  fallback: string,
  labelMap: Record<string, string>
): string => {
  const rawLabel = getIndexedLabel(value, labels, fallback)
  return labelMap[rawLabel] || rawLabel
}

const formatDateTime = (value: unknown): string => {
  const text = String(value || '').trim()
  if (!text) return '-'
  const parsed = new Date(text)
  if (Number.isNaN(parsed.getTime())) return text

  const year = parsed.getFullYear()
  const month = String(parsed.getMonth() + 1).padStart(2, '0')
  const day = String(parsed.getDate()).padStart(2, '0')
  const hour = String(parsed.getHours()).padStart(2, '0')
  const minute = String(parsed.getMinutes()).padStart(2, '0')
  const second = String(parsed.getSeconds()).padStart(2, '0')
  return `${year}-${month}-${day} ${hour}:${minute}:${second}`
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

const normalizeProductCategoryLabels = (value: unknown): string => {
  if (!Array.isArray(value)) return '（空）'
  const labels = value
    .map((item) => {
      const key = String(item || '').trim()
      return PRODUCT_CATEGORY_LABEL_MAP[key] || key
    })
    .filter(Boolean)
  return labels.join(', ') || '（空）'
}

const normalizeRuntimeRows = (rawList: unknown, taskId: string): RuntimeRow[] => {
  if (!Array.isArray(rawList) || rawList.length === 0) {
    return []
  }

  return rawList.map((item: any, index: number) => ({
    id: String(item?.id ?? item?.creatorId ?? `${taskId}-runtime-${index + 1}`),
    creatorName: String(item?.creatorName ?? item?.name ?? item?.nickname ?? '-'),
    followers: String(item?.followers ?? item?.fansCount ?? item?.followerCount ?? '-'),
    gmv: String(item?.gmv ?? item?.gmvRange ?? '-'),
    outreachTask: String(item?.taskName ?? item?.outreachTask ?? item?.taskAction ?? item?.messageType ?? '-'),
    messageTime: formatDateTime(item?.sendTime ?? item?.messageTime ?? item?.sentAt ?? item?.createdAt ?? '-')
  }))
}

const buildDetailFromSource = (source: Record<string, any>, fallbackTask?: TaskInfo | null): TaskDetailData => {
  const filterConfig = source.filterConfig || {}
  const creatorFilter = source.creatorFilter || {}
  const creatorFilters = filterConfig.creatorFilters || {}
  const followerFilters = filterConfig.followerFilters || {}
  const performanceFilters = filterConfig.performanceFilters || {}
  const searchKeyword = String(filterConfig.searchKeyword ?? creatorFilter.keyword ?? '').trim()

  const productCategories = Array.isArray(creatorFilters.productCategorySelections)
    ? normalizeProductCategoryLabels(creatorFilters.productCategorySelections)
    : normalizeProductCategoryLabels(creatorFilter.productCategories)

  const avgCommissionRateLabel = getMappedLabel(
    creatorFilter.avgCommissionRate ?? creatorFilters.avgCommissionRate,
    AVG_COMMISSION_RATE_LABELS,
    'All',
    OUTREACH_AVG_COMMISSION_RATE_LABEL_MAP
  )
  const contentTypeLabel = getMappedLabel(
    creatorFilter.contentTypes ?? creatorFilters.contentType,
    CONTENT_TYPE_LABELS,
    'All',
    OUTREACH_CONTENT_TYPE_LABEL_MAP
  )
  const creatorAgencyLabel = getMappedLabel(
    creatorFilter.creatorAgency ?? creatorFilters.creatorAgency,
    CREATOR_AGENCY_LABELS,
    'All',
    OUTREACH_CREATOR_AGENCY_LABEL_MAP
  )
  const fansGenderLabel = getMappedLabel(
    creatorFilter.fansGender ?? followerFilters.followerGender,
    FOLLOWER_GENDER_LABELS,
    'All',
    OUTREACH_FOLLOWER_GENDER_LABEL_MAP
  )
  const fansAgeRange = Array.isArray(creatorFilter.fansAgeRange)
    ? creatorFilter.fansAgeRange.join(', ')
    : Array.isArray(followerFilters.followerAgeSelections)
      ? followerFilters.followerAgeSelections.join(', ')
      : ''
  const gmvRange = Array.isArray(creatorFilter.gmvRange)
    ? creatorFilter.gmvRange.join(', ')
    : Array.isArray(performanceFilters.gmvSelections)
      ? performanceFilters.gmvSelections.join(', ')
      : ''
  const salesCountRange = Array.isArray(creatorFilter.salesCountRange)
    ? creatorFilter.salesCountRange.join(', ')
    : Array.isArray(performanceFilters.itemsSoldSelections)
      ? performanceFilters.itemsSoldSelections.join(', ')
      : ''
  const coBranding = Array.isArray(creatorFilter.coBranding) ? creatorFilter.coBranding.join(', ') : ''
  const fansCountMin = String(followerFilters.followerCountMin ?? creatorFilter.fansCountRange?.min ?? '0')
  const fansCountMax = String(followerFilters.followerCountMax ?? creatorFilter.fansCountRange?.max ?? '10,000,000+')

  const filterSummary = [
    `关键词：${searchKeyword || '（空）'}`,
    `商品类目：${productCategories}`,
    `平均佣金率：${avgCommissionRateLabel}`,
    `内容类型：${contentTypeLabel}`,
    `达人机构：${creatorAgencyLabel}`,
    `快速成长榜：${creatorFilter.fastGrowing ? '是' : '否'}`,
    `过去 90 天内未获邀请的达人：${creatorFilter.notInvitedInPast90Days ? '是' : '否'}`,
    `粉丝年龄：${fansAgeRange || '（空）'}`,
    `粉丝性别：${fansGenderLabel}`,
    `粉丝数：${fansCountMin} - ${fansCountMax}`,
    `GMV：${gmvRange || '（空）'}`,
    `成交件数：${salesCountRange || '（空）'}`,
    `平均每个视频的播放量：${String(creatorFilter.minAvgVideoViews ?? performanceFilters.averageViewsPerVideoMin ?? '0')}`,
    `平均每场直播的观看人数：${String(creatorFilter.minAvgLiveViews ?? performanceFilters.averageViewersPerLiveMin ?? '0')}`,
    `互动率 (%)：${String(creatorFilter.minEngagementRate ?? performanceFilters.engagementRateMinPercent ?? '0')}`,
    `品牌合作：${coBranding || '（空）'}`
  ]

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
    startTime: formatDateTime(source.startTime || fallbackTask?.startTime || '-'),
    status: normalizeStatusToUI(source.status || fallbackTask?.status),
    progress: {
      linked: toNumber(source.linkedCount ?? source.realCount ?? source.completedCount ?? fallbackTask?.linkedCount, 0),
      total: toNumber(source.planCount ?? source.plannedCount ?? fallbackTask?.planCount, 0)
    },
    filterSummary,
    creatorSortLabel:
      SORT_LABEL_MAP[String(source.creatorSort ?? source.creatorFilter?.sortBy ?? 'OFFICIAL_DEFAULT')] ||
      String(source.creatorSort ?? source.creatorFilter?.sortBy ?? '官方默认值'),
    outreachCreatorTypeLabel:
      OUTREACH_CREATOR_TYPE_LABEL_MAP[creatorType as keyof typeof OUTREACH_CREATOR_TYPE_LABEL_MAP] || '建联所有达人',
    messageTemplate: {
      firstMessage,
      replyMessage
    },
    runtimeRows: []
  }
}

const buildDetailFromTask = (task: TaskInfo): TaskDetailData => {
  return buildDetailFromSource(task.raw || {}, task)
}

const fetchRuntimeRows = async (): Promise<void> => {
  const taskId = currentTaskId.value
  if (!taskId) {
    runtimeRows.value = []
    runtimeTotal.value = 0
    return
  }

  isRuntimeLoading.value = true
  try {
    const result = await getOutreachTaskRecords(taskId, {
      page: runtimePage.value,
      pageSize: runtimePageSize.value
    })
    runtimeRows.value = normalizeRuntimeRows(result.list, taskId)
    runtimeTotal.value = Number(result.total || 0)
  } catch (_error) {
    runtimeRows.value = []
    runtimeTotal.value = 0
  } finally {
    isRuntimeLoading.value = false
  }
}

const fetchTaskDetail = async (): Promise<void> => {
  const taskId = currentTaskId.value
  if (!taskId && !props.task) {
    detail.value = null
    errorMessage.value = '未找到任务详情，请返回列表后重试'
    runtimeRows.value = []
    runtimeTotal.value = 0
    return
  }

  isLoading.value = true
  errorMessage.value = ''

  try {
    if (taskId) {
      const result = await getOutreachTaskDetail(taskId)
      const payload = (result?.data ?? result ?? {}) as Record<string, any>
      detail.value = buildDetailFromSource(payload, props.task)
    } else if (props.task) {
      detail.value = buildDetailFromTask(props.task)
    } else {
      detail.value = null
      errorMessage.value = '未找到任务详情，请返回列表后重试'
    }
  } catch (_error) {
    if (props.task) {
      detail.value = buildDetailFromTask(props.task)
      errorMessage.value = ''
    } else {
      detail.value = null
      errorMessage.value = '加载任务详情失败'
    }
  } finally {
    isLoading.value = false
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
    if (!shouldPollTaskDetail.value || isLoading.value || isRuntimeLoading.value) return
    void fetchTaskDetail()
    void fetchRuntimeRows()
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

      <NCard class="detail-section-card" :bordered="false" size="small" title="筛选达人">
        <NList class="summary-list" :bordered="false" hoverable>
          <NListItem v-for="(item, index) in detail.filterSummary" :key="index" class="summary-list-item">
            {{ item }}
          </NListItem>
        </NList>
      </NCard>

      <NCard class="detail-section-card" :bordered="false" size="small" title="达人排序">
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
            :scroll-x="760"
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
  border: 1px solid #dbe5f3;
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
  padding: 0;
}

.detail-section-card:deep(.n-card-header) {
  padding: 14px 14px 0;
}

.detail-section-card:deep(.n-card-header__main) {
  color: #1f2d3d;
  font-size: 16px;
  font-weight: 600;
}

.detail-section-card:deep(.n-card__content) {
  padding: 10px 14px 14px;
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

.runtime-data-table:deep(.n-data-table-th) {
  background: #f8fafc;
  color: #4b5c71;
  font-weight: 600;
}

.runtime-data-table:deep(.n-data-table-td) {
  color: #334155;
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
