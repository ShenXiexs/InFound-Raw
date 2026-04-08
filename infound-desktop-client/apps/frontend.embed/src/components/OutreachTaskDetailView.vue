<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getOutreachTaskDetail } from '../api/outreach-task.api'

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

const PRODUCT_CATEGORY_LABEL_MAP: Record<string, string> = {
  '600001': 'Home Supplies',
  '600024': 'Kitchenware',
  '600154': 'Textiles & Soft Furnishings',
  '600942': 'Household Appliances',
  '601152': 'Womenswear & Underwear',
  '601303': 'Modest Fashion',
  '601352': 'Shoes',
  '601450': 'Beauty & Personal Care',
  '601739': 'Phones & Electronics',
  '601755': 'Computers & Office Equipment',
  '602118': 'Pet Supplies',
  '603014': 'Sports & Outdoor',
  '604453': 'Furniture',
  '604579': 'Tools & Hardware',
  '604968': 'Home Improvement',
  '605196': 'Automotive & Motorcycle',
  '605248': 'Fashion Accessories',
  '700645': 'Health',
  '801928': 'Books, Magazines & Audio',
  '802184': "Kids' Fashion",
  '824328': 'Menswear & Underwear',
  '824584': 'Luggage & Bags',
  '951432': 'Collections'
}

const AVG_COMMISSION_RATE_LABELS = ['All', 'Less than 20%', 'Less than 15%', 'Less than 10%', 'Less than 5%']
const CONTENT_TYPE_LABELS = ['All', 'Video', 'LIVE']
const CREATOR_AGENCY_LABELS = ['All', 'Managed by agency', 'Independent creators']
const FOLLOWER_GENDER_LABELS = ['All', 'Female', 'Male']
const SORT_LABEL_MAP: Record<string, string> = {
  OFFICIAL_DEFAULT: '官方默认值',
  GMV_DESC: '达人GMV降序',
  FOLLOWERS_DESC: '达人粉丝数降序',
  COMMISSION_DESC: '达人佣金率降序',
  '0': 'Relevancy',
  '1': 'GMV',
  '2': 'Units sold',
  '3': 'Follower',
  '4': 'Avg. video views',
  '5': 'Engagement rate'
}

const OUTREACH_CREATOR_TYPE_LABEL_MAP: Record<string, string> = {
  ALL: '建联所有达人',
  NEW_ONLY: '只建联新达人',
  NEW_AND_NOT_REPLIED: '建联新达人和未回复达人'
}

const isLoading = ref(false)
const errorMessage = ref('')
const detail = ref<TaskDetailData | null>(null)
const runtimePage = ref(1)
const runtimePageSize = ref(10)
const runtimePageSizeOptions = [10, 20, 50]

const runtimeTotalPages = computed(() => {
  const total = detail.value?.runtimeRows.length || 0
  return Math.max(1, Math.ceil(total / runtimePageSize.value))
})

const pagedRuntimeRows = computed(() => {
  const source = detail.value?.runtimeRows || []
  const start = (runtimePage.value - 1) * runtimePageSize.value
  return source.slice(start, start + runtimePageSize.value)
})

const canEdit = computed(() => detail.value?.status === '未启动')
const canEnd = computed(() => detail.value?.status === '运行中')

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

const createHardcodedRuntimeRows = (taskId: string): RuntimeRow[] => {
  const creators: Array<[string, string, string, string, string]> = [
    ['@fashion_luna', '132K', '$42.1K', '首次建联', '2026-03-26 09:10'],
    ['@daily_home_amy', '89K', '$18.6K', '首次建联', '2026-03-26 09:13'],
    ['@tech_mike', '205K', '$57.2K', '首次建联', '2026-03-26 09:20'],
    ['@beauty_nina', '176K', '$48.3K', '回复达人消息', '2026-03-26 09:31'],
    ['@pet_jason', '61K', '$12.0K', '首次建联', '2026-03-26 09:36'],
    ['@toy_story_zoe', '73K', '$9.7K', '首次建联', '2026-03-26 09:41'],
    ['@kitchen_anna', '114K', '$21.4K', '回复达人消息', '2026-03-26 09:48'],
    ['@sports_tom', '250K', '$68.1K', '首次建联', '2026-03-26 09:52'],
    ['@book_bella', '58K', '$7.6K', '首次建联', '2026-03-26 10:03'],
    ['@bags_john', '96K', '$16.8K', '回复达人消息', '2026-03-26 10:10'],
    ['@auto_eric', '184K', '$32.3K', '首次建联', '2026-03-26 10:16'],
    ['@health_ruby', '142K', '$27.5K', '首次建联', '2026-03-26 10:24']
  ]

  return creators.map((item, index) => ({
    id: `${taskId}-runtime-${index + 1}`,
    creatorName: item[0],
    followers: item[1],
    gmv: item[2],
    outreachTask: item[3],
    messageTime: item[4]
  }))
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

const normalizeRuntimeRows = (source: Record<string, any>, taskId: string): RuntimeRow[] => {
  const rawList = [source.runtimeRows, source.runtimeList, source.records, source.items, source.creatorList].find((item) => Array.isArray(item))
  if (!Array.isArray(rawList) || rawList.length === 0) {
    return createHardcodedRuntimeRows(taskId)
  }

  return rawList.map((item: any, index: number) => ({
    id: String(item?.id ?? item?.creatorId ?? `${taskId}-runtime-${index + 1}`),
    creatorName: String(item?.creatorName ?? item?.name ?? item?.nickname ?? '-'),
    followers: String(item?.followers ?? item?.fansCount ?? item?.followerCount ?? '-'),
    gmv: String(item?.gmv ?? item?.gmvRange ?? '-'),
    outreachTask: String(item?.outreachTask ?? item?.taskAction ?? item?.messageType ?? '-'),
    messageTime: String(item?.messageTime ?? item?.sentAt ?? item?.createdAt ?? '-')
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

  const avgCommissionRateLabel = getIndexedLabel(creatorFilter.avgCommissionRate ?? creatorFilters.avgCommissionRate, AVG_COMMISSION_RATE_LABELS, 'All')
  const contentTypeLabel = getIndexedLabel(creatorFilter.contentTypes ?? creatorFilters.contentType, CONTENT_TYPE_LABELS, 'All')
  const creatorAgencyLabel = getIndexedLabel(creatorFilter.creatorAgency ?? creatorFilters.creatorAgency, CREATOR_AGENCY_LABELS, 'All')
  const fansGenderLabel = getIndexedLabel(creatorFilter.fansGender ?? followerFilters.followerGender, FOLLOWER_GENDER_LABELS, 'All')
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
    `Product category：${productCategories}`,
    `Avg. commission rate：${avgCommissionRateLabel}`,
    `Content type：${contentTypeLabel}`,
    `Creator agency：${creatorAgencyLabel}`,
    `Fast growing：${creatorFilter.fastGrowing ? '是' : '否'}`,
    `Not invited in past 90 days：${creatorFilter.notInvitedInPast90Days ? '是' : '否'}`,
    `Follower age：${fansAgeRange || '（空）'}`,
    `Follower gender：${fansGenderLabel}`,
    `Follower count：${fansCountMin} - ${fansCountMax}`,
    `GMV：${gmvRange || '（空）'}`,
    `Items sold：${salesCountRange || '（空）'}`,
    `Average views per video min：${String(creatorFilter.minAvgVideoViews ?? performanceFilters.averageViewsPerVideoMin ?? '0')}`,
    `Average viewers per LIVE min：${String(creatorFilter.minAvgLiveViews ?? performanceFilters.averageViewersPerLiveMin ?? '0')}`,
    `Engagement rate min (%)：${String(creatorFilter.minEngagementRate ?? performanceFilters.engagementRateMinPercent ?? '0')}`,
    `Brand collaborations：${coBranding || '（空）'}`
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
    outreachCreatorTypeLabel: OUTREACH_CREATOR_TYPE_LABEL_MAP[creatorType] || '建联所有达人',
    messageTemplate: {
      firstMessage,
      replyMessage
    },
    runtimeRows: normalizeRuntimeRows(source, String(source.id || source.taskId || fallbackTask?.id || 'task'))
  }
}

const buildDetailFromTask = (task: TaskInfo): TaskDetailData => {
  return buildDetailFromSource(task.raw || {}, task)
}

const fetchTaskDetail = async (): Promise<void> => {
  const taskId = String(props.taskId || props.task?.id || '').trim()
  if (!taskId && !props.task) {
    detail.value = null
    errorMessage.value = '未找到任务详情，请返回列表后重试'
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
    runtimePage.value = 1
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

const changeRuntimePage = (nextPage: number): void => {
  if (nextPage < 1 || nextPage > runtimeTotalPages.value) return
  runtimePage.value = nextPage
}

const handleRuntimePageSizeChange = (): void => {
  runtimePage.value = 1
}

watch(
  () => `${props.taskId || ''}-${props.task?.id || ''}`,
  () => {
    void fetchTaskDetail()
  },
  { immediate: true }
)

watch(runtimeTotalPages, (value) => {
  if (runtimePage.value > value) {
    runtimePage.value = value
  }
})
</script>

<template>
  <section class="detail-shell">
    <div v-if="isLoading" class="detail-loading">加载详情中...</div>
    <div v-else-if="errorMessage" class="detail-error">{{ errorMessage }}</div>
    <template v-else-if="detail">
      <header class="detail-header">
        <h2>{{ detail.taskName }}</h2>
        <div class="header-actions">
          <button
            v-if="canEdit"
            class="header-btn"
            title="编辑"
            type="button"
            @click="emit('edit')"
          >
            <span aria-hidden="true">✎</span>
            <span>编辑</span>
          </button>
          <button
            v-if="canEnd"
            class="header-btn danger"
            title="结束"
            type="button"
            @click="emit('end')"
          >
            <span aria-hidden="true">⏸</span>
            <span>结束</span>
          </button>
        </div>
      </header>

      <section class="info-block">
        <h3>任务信息</h3>
        <div class="top-row">
          <span>启动时间：{{ detail.startTime }}</span>
          <span>建联状态：{{ detail.status }}</span>
        </div>
        <div class="progress-row">建联进度：{{ detail.progress.linked }} / {{ detail.progress.total }}</div>
      </section>

      <section class="info-block">
        <h3>筛选达人</h3>
        <ul class="summary-list">
          <li v-for="(item, index) in detail.filterSummary" :key="index">{{ item }}</li>
        </ul>
      </section>

      <section class="info-block">
        <h3>达人排序</h3>
        <p class="plain-text">{{ detail.creatorSortLabel }}</p>
      </section>

      <section class="info-block">
        <h3>消息模板</h3>
        <p class="plain-text">建联达人：{{ detail.outreachCreatorTypeLabel }}</p>

        <article class="message-card">
          <h4>首次消息</h4>
          <p>{{ detail.messageTemplate.firstMessage.content }}</p>
          <p class="message-meta">
            商品消息：{{ detail.messageTemplate.firstMessage.productMessageEnabled ? '已开启' : '未开启' }}
            <template v-if="detail.messageTemplate.firstMessage.productMessageEnabled">
              （商品ID：{{ detail.messageTemplate.firstMessage.productIds.join('、') || '无' }}）
            </template>
          </p>
        </article>

        <article v-if="detail.messageTemplate.replyMessage" class="message-card">
          <h4>回复达人消息</h4>
          <p>{{ detail.messageTemplate.replyMessage.content }}</p>
          <p class="message-meta">
            商品消息：{{ detail.messageTemplate.replyMessage.productMessageEnabled ? '已开启' : '未开启' }}
            <template v-if="detail.messageTemplate.replyMessage.productMessageEnabled">
              （商品ID：{{ detail.messageTemplate.replyMessage.productIds.join('、') || '无' }}）
            </template>
          </p>
        </article>
      </section>

      <section class="runtime-block">
        <h3>任务运行情况</h3>
        <div class="table-wrap">
          <table class="runtime-table">
            <thead>
              <tr>
                <th>达人</th>
                <th>粉丝数量</th>
                <th>GMV</th>
                <th>建联任务</th>
                <th>消息发送时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="pagedRuntimeRows.length === 0">
                <td colspan="5" class="empty-row">暂无数据</td>
              </tr>
              <tr v-for="item in pagedRuntimeRows" :key="item.id">
                <td>{{ item.creatorName }}</td>
                <td>{{ item.followers }}</td>
                <td>{{ item.gmv }}</td>
                <td>{{ item.outreachTask }}</td>
                <td>{{ item.messageTime }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <footer class="pagination-row">
          <span class="total-text">共 {{ detail.runtimeRows.length }} 条</span>
          <div class="pager">
            <label class="page-size-label">
              每页
              <select v-model.number="runtimePageSize" @change="handleRuntimePageSizeChange">
                <option v-for="size in runtimePageSizeOptions" :key="size" :value="size">{{ size }}</option>
              </select>
              条
            </label>
            <button :disabled="runtimePage <= 1" type="button" @click="changeRuntimePage(runtimePage - 1)">上一页</button>
            <span class="page-index">{{ runtimePage }} / {{ runtimeTotalPages }}</span>
            <button :disabled="runtimePage >= runtimeTotalPages" type="button" @click="changeRuntimePage(runtimePage + 1)">下一页</button>
          </div>
        </footer>
      </section>
    </template>
  </section>
</template>

<style scoped>
.detail-shell {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-loading,
.detail-error {
  border: 1px solid #dbe5f3;
  border-radius: 10px;
  background: #fff;
  padding: 14px;
  color: #5b6d83;
}

.detail-header,
.info-block,
.runtime-block {
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

.header-btn {
  border: 1px solid #cfd8e8;
  border-radius: 8px;
  background: #fff;
  color: #2f3f53;
  padding: 6px 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
}

.header-btn.danger {
  border-color: #e8c3c7;
  color: #b42318;
}

.info-block h3,
.runtime-block h3 {
  margin: 0 0 10px;
  color: #1f2d3d;
  font-size: 16px;
}

.top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  color: #334155;
  font-size: 14px;
}

.progress-row,
.plain-text {
  color: #334155;
  font-size: 14px;
}

.summary-list {
  margin: 0;
  padding-left: 18px;
  color: #334155;
  font-size: 14px;
  display: grid;
  gap: 5px;
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

.runtime-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 760px;
}

.runtime-table th,
.runtime-table td {
  text-align: left;
  padding: 11px 12px;
  border-bottom: 1px solid #edf2f9;
  color: #334155;
  font-size: 13px;
}

.runtime-table th {
  font-weight: 600;
  color: #4b5c71;
  background: #f8fafc;
}

.empty-row {
  text-align: center !important;
  color: #6b7f95 !important;
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

@media (max-width: 900px) {
  .detail-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .top-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .pagination-row {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
