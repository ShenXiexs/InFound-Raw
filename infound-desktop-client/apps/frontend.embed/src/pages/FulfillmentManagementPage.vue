<script setup lang="ts">
import { computed, h, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import {
  createDiscreteApi,
  dateZhCN,
  NButton,
  NCard,
  NDataTable,
  NDescriptions,
  NDescriptionsItem,
  NFlex,
  NInput,
  NModal,
  NPagination,
  NSpace,
  NSwitch,
  zhCN,
  type DataTableColumns
} from 'naive-ui'
import {
  getFulfillmentReminderLast24hCount,
  getFulfillmentReminderRecordList,
  getFulfillmentRuleList,
  setFulfillmentRuleEnabled,
  updateFulfillmentRule,
  type FulfillmentRuleItem as ApiFulfillmentRuleItem
} from '../api/fulfillment.api'
import { formatDateTimeToLocal } from '../utils/date-time'

interface FulfillmentRuleItem {
  id: string
  ruleCode: string
  ruleName: string
  ruleDescription: string
  ruleEvent: string
  ruleMessage: string
  enabled: boolean
  configured: boolean
  canEnable: boolean
}

interface RuleConfigFormState {
  enabled: boolean
  message: string
}

interface FulfillmentReminderItem {
  id: string
  creatorName: string
  followerCount: string
  gmv: string
  matchedRule: string
  sentAt: string
}

type FulfillmentView = 'list' | 'config' | 'reminders'

const RULE_MESSAGE_MAX_LENGTH = 2000

interface FulfillmentRoute {
  view: FulfillmentView
  ruleId?: string
}

const props = defineProps<{
  shopId?: string
}>()

const { message } = createDiscreteApi(['message'], {
  configProviderProps: {
    locale: zhCN,
    dateLocale: dateZhCN
  }
})

const reminderCount = ref(0)
const reminderPage = ref(1)
const reminderPageSize = 4
const isLoading = ref(false)
const errorMessage = ref('')
const isReminderLoading = ref(false)
const reminderErrorMessage = ref('')
const ruleList = ref<FulfillmentRuleItem[]>([])
const reminderList = ref<FulfillmentReminderItem[]>([])
const togglingRuleIds = ref<string[]>([])
const currentView = ref<FulfillmentView>('list')
const activeRuleId = ref('')
const isConfigSaving = ref(false)
const configForm = reactive<RuleConfigFormState>({
  enabled: false,
  message: ''
})

const reminderTotal = ref(0)
const reminderTotalPages = computed(() => Math.max(1, Math.ceil(reminderTotal.value / reminderPageSize)))
const pagedReminders = computed(() => reminderList.value)
const activeRule = computed(() => ruleList.value.find((item) => item.id === activeRuleId.value) || null)
const configRuleName = computed(() => activeRule.value?.ruleName || activeRule.value?.ruleCode || '-')
const configRuleDescription = computed(() => activeRule.value?.ruleDescription || '-')
const configRuleEvent = computed(() => activeRule.value?.ruleEvent || '-')
const ruleMessageLength = computed(() => configForm.message.length)
const isRuleMessageTooLong = computed(() => ruleMessageLength.value > RULE_MESSAGE_MAX_LENGTH)
const isConfigModalVisible = computed(() => currentView.value === 'config')
const isReminderModalVisible = computed(() => currentView.value === 'reminders')
const isRuleToggling = (ruleId: string): boolean => togglingRuleIds.value.includes(ruleId)
const ruleTableEmptyText = computed(() => errorMessage.value || '暂无履约规则')
const reminderTableEmptyText = computed(() => reminderErrorMessage.value || '暂无提醒记录')

const ruleColumns: DataTableColumns<FulfillmentRuleItem> = [
  {
    title: '规则名称',
    key: 'ruleName',
    minWidth: 180,
    render: (row) => h('span', { class: 'rule-name' }, row.ruleName)
  },
  {
    title: '规则说明',
    key: 'ruleDescription',
    minWidth: 220
  },
  {
    title: '规则事件',
    key: 'ruleEvent',
    minWidth: 220
  },
  {
    title: '是否启用',
    key: 'enabled',
    width: 150,
    render: (row) =>
      h(
        NSpace,
        {
          align: 'center',
          size: 8
        },
        {
          default: () => [
            h('span', row.enabled ? '已启用' : '未启用'),
            h(NSwitch, {
              value: row.enabled,
              loading: isRuleToggling(row.id),
              disabled: isRuleToggling(row.id),
              'onUpdate:value': () => {
                void toggleRule(row.id)
              }
            })
          ]
        }
      )
  },
  {
    title: '操作',
    key: 'actions',
    width: 120,
    render: (row) =>
      h(
        NButton,
        {
          text: true,
          type: 'primary',
          onClick: () => configureRule(row.id)
        },
        {
          default: () => (row.configured ? '配置' : '待配置')
        }
      )
  }
]

const reminderColumns: DataTableColumns<FulfillmentReminderItem> = [
  {
    title: '达人',
    key: 'creatorName',
    minWidth: 150
  },
  {
    title: '粉丝数量',
    key: 'followerCount',
    width: 120
  },
  {
    title: 'GMV',
    key: 'gmv',
    width: 120
  },
  {
    title: '命中规则',
    key: 'matchedRule',
    minWidth: 160
  },
  {
    title: '发送提醒时间',
    key: 'sentAt',
    minWidth: 180
  }
]

watch(reminderTotalPages, (value) => {
  if (reminderPage.value > value) {
    reminderPage.value = value
  }
})

const showActionMessage = (content: string, type: 'success' | 'error' | 'warning' | 'info' = 'info'): void => {
  message[type](content, {
    duration: 2200
  })
}

const normalizeRuleItem = (item: ApiFulfillmentRuleItem, index: number): FulfillmentRuleItem => {
  return {
    id: String(item.ruleCode || item.name || index),
    ruleCode: String(item.ruleCode || ''),
    ruleName: String(item.name || '-'),
    ruleDescription: String(item.description || '-'),
    ruleEvent: String(item.remark || '-'),
    ruleMessage: String(item.message || ''),
    enabled: Boolean(item.isActive),
    configured: Boolean(item.isConfigured),
    canEnable: Boolean(item.canEnable)
  }
}

const toDisplayText = (value: unknown, fallback: string = '-'): string => {
  const text = typeof value === 'string' ? value.trim() : value == null ? '' : String(value).trim()
  return text || fallback
}

const normalizeReminderItem = (item: Record<string, any>, index: number): FulfillmentReminderItem => {
  return {
    id: toDisplayText(item.id ?? item.recordId ?? item.creatorId ?? item.platformCreatorId ?? index, `reminder-${index}`),
    creatorName: toDisplayText(item.creator ?? item.creatorName ?? item.creator_name ?? item.nickname ?? item.creatorNickName),
    followerCount: toDisplayText(item.followers ?? item.followerCount ?? item.fansCount ?? item.follower_count ?? item.fans_count),
    gmv: toDisplayText(item.gmv ?? item.gmvAmount ?? item.gmv_amount),
    matchedRule: toDisplayText(item.hitRule ?? item.matchedRule ?? item.ruleName ?? item.ruleCode ?? item.rule_code),
    sentAt: formatDateTimeToLocal(item.remindAt ?? item.sentAt ?? item.sendTime ?? item.createdAt ?? item.created_at)
  }
}

const parseHashRoute = (): FulfillmentRoute => {
  const rawHash = window.location.hash || '#/fulfillment'
  const [pathPart = '', queryPart = ''] = rawHash.replace(/^#/, '').split('?')
  if (!pathPart.toLowerCase().includes('/fulfillment')) {
    return { view: 'list' }
  }

  const query = new URLSearchParams(queryPart)
  const viewParam = (query.get('view') || 'list').toLowerCase()
  const ruleId = query.get('ruleId')?.trim() || ''

  if (viewParam === 'config' && ruleId) {
    return { view: 'config', ruleId }
  }
  if (viewParam === 'reminders') {
    return { view: 'reminders' }
  }

  return { view: 'list' }
}

const buildHash = (route: FulfillmentRoute): string => {
  if (route.view === 'list') {
    return '#/fulfillment'
  }

  const query = new URLSearchParams()
  query.set('view', route.view)
  if (route.ruleId) query.set('ruleId', route.ruleId)
  return `#/fulfillment?${query.toString()}`
}

const syncConfigForm = (rule: FulfillmentRuleItem): void => {
  configForm.enabled = rule.enabled
  configForm.message = rule.ruleMessage
}

const openConfigView = (ruleId: string): void => {
  const current = ruleList.value.find((item) => item.id === ruleId)
  if (!current) return
  currentView.value = 'config'
  activeRuleId.value = ruleId
  syncConfigForm(current)
}

const applyRoute = (route: FulfillmentRoute): void => {
  if (route.view === 'config' && route.ruleId) {
    const target = ruleList.value.find((item) => item.id === route.ruleId)
    if (target) {
      openConfigView(target.id)
      return
    }
  }
  if (route.view === 'reminders') {
    currentView.value = 'reminders'
    activeRuleId.value = ''
    void fetchReminderList()
    return
  }

  currentView.value = 'list'
  activeRuleId.value = ''
}

const navigate = (route: FulfillmentRoute): void => {
  const nextHash = buildHash(route)
  if (window.location.hash !== nextHash) {
    window.location.hash = nextHash
    return
  }

  applyRoute(route)
}

const fetchRuleList = async (): Promise<void> => {
  const shopId = props.shopId?.trim() || ''
  if (!shopId) {
    ruleList.value = []
    reminderList.value = []
    reminderTotal.value = 0
    errorMessage.value = '缺少 shopId，无法加载履约规则'
    applyRoute({ view: 'list' })
    return
  }

  isLoading.value = true
  try {
    const result = await getFulfillmentRuleList(shopId)
    ruleList.value = result.map(normalizeRuleItem)
    errorMessage.value = ''
  } catch (error: any) {
    ruleList.value = []
    reminderList.value = []
    reminderTotal.value = 0
    errorMessage.value = error?.message || '履约规则加载失败'
  } finally {
    isLoading.value = false
    applyRoute(parseHashRoute())
  }
}

const fetchReminderCount = async (): Promise<void> => {
  const shopId = props.shopId?.trim() || ''
  if (!shopId) {
    reminderCount.value = 0
    return
  }

  try {
    reminderCount.value = await getFulfillmentReminderLast24hCount(shopId)
  } catch (_error) {
    reminderCount.value = 0
  }
}

const fetchReminderList = async (): Promise<void> => {
  const shopId = props.shopId?.trim() || ''
  if (!shopId) {
    reminderList.value = []
    reminderTotal.value = 0
    reminderErrorMessage.value = '缺少 shopId，无法加载提醒记录'
    return
  }

  isReminderLoading.value = true
  reminderErrorMessage.value = ''
  try {
    const result = await getFulfillmentReminderRecordList(
      {
        page: reminderPage.value,
        pageSize: reminderPageSize
      },
      {
        shopId,
        ruleCode: ''
      }
    )
    reminderList.value = result.list.map((item, index) => normalizeReminderItem(item, index))
    reminderTotal.value = result.total
  } catch (error: any) {
    reminderList.value = []
    reminderTotal.value = 0
    reminderErrorMessage.value = error?.message || '提醒记录加载失败'
  } finally {
    isReminderLoading.value = false
  }
}

const toggleRule = async (ruleId: string): Promise<void> => {
  const index = ruleList.value.findIndex((item) => item.id === ruleId)
  if (index < 0) return

  const current = ruleList.value[index]
  if (!current) return
  if (isRuleToggling(ruleId)) return

  if (!current.enabled && !current.canEnable) {
    showActionMessage('当前规则不可启用，请先完成规则配置', 'warning')
    return
  }

  const shopId = props.shopId?.trim() || ''
  if (!shopId) {
    showActionMessage('缺少 shopId，无法更新规则状态', 'error')
    return
  }

  const nextEnabled = !current.enabled
  togglingRuleIds.value = [...togglingRuleIds.value, ruleId]

  try {
    await setFulfillmentRuleEnabled(current.ruleCode, {
      shopId,
      message: current.ruleMessage || '',
      isActive: String(nextEnabled)
    })
    ruleList.value.splice(index, 1, {
      ...current,
      enabled: nextEnabled
    })
    showActionMessage(nextEnabled ? '规则已启用' : '规则已停用', 'success')
  } catch (error: any) {
    if (error?.response?.status === 404) {
      ruleList.value.splice(index, 1, {
        ...current,
        enabled: nextEnabled
      })
      showActionMessage('启停接口未发布，当前仅更新本地显示', 'warning')
    } else {
      showActionMessage(error?.message || '规则启停失败', 'error')
    }
  } finally {
    togglingRuleIds.value = togglingRuleIds.value.filter((item) => item !== ruleId)
  }
}

const configureRule = (ruleId: string): void => {
  const current = ruleList.value.find((item) => item.id === ruleId)
  if (!current) return
  navigate({ view: 'config', ruleId: current.id })
}

const openReminderView = (): void => {
  reminderPage.value = 1
  navigate({ view: 'reminders' })
}

const cancelConfig = (): void => {
  navigate({ view: 'list' })
}

const backToRuleList = (): void => {
  navigate({ view: 'list' })
}

const handleConfigModalShowChange = (value: boolean): void => {
  if (!value && isConfigModalVisible.value) {
    cancelConfig()
  }
}

const handleReminderModalShowChange = (value: boolean): void => {
  if (!value && isReminderModalVisible.value) {
    backToRuleList()
  }
}

const saveRuleConfig = async (): Promise<void> => {
  const current = activeRule.value
  if (!current) {
    navigate({ view: 'list' })
    return
  }

  const index = ruleList.value.findIndex((item) => item.id === current.id)
  if (index < 0) {
    navigate({ view: 'list' })
    return
  }

  const shopId = props.shopId?.trim() || ''
  if (!shopId) {
    showActionMessage('缺少 shopId，无法保存规则配置', 'error')
    return
  }

  if (isConfigSaving.value) {
    return
  }

  const nextMessage = configForm.message.trim()
  if (nextMessage.length > RULE_MESSAGE_MAX_LENGTH) {
    showActionMessage(`提醒消息需在 ${RULE_MESSAGE_MAX_LENGTH} 字内`, 'warning')
    return
  }
  const nextEnabled = configForm.enabled
  isConfigSaving.value = true

  try {
    await updateFulfillmentRule(current.ruleCode, {
      shopId,
      message: nextMessage,
      isActive: String(nextEnabled)
    })
    ruleList.value.splice(index, 1, {
      ...current,
      enabled: nextEnabled,
      configured: true,
      canEnable: true,
      ruleMessage: nextMessage
    })
    showActionMessage('规则配置已保存', 'success')
    navigate({ view: 'list' })
  } catch (error: any) {
    if (error?.response?.status === 404) {
      ruleList.value.splice(index, 1, {
        ...current,
        enabled: nextEnabled,
        configured: true,
        canEnable: true,
        ruleMessage: nextMessage
      })
      showActionMessage('配置接口未发布，当前仅更新本地显示', 'warning')
      navigate({ view: 'list' })
    } else {
      showActionMessage(error?.message || '保存规则配置失败', 'error')
    }
  } finally {
    isConfigSaving.value = false
  }
}

const handleHashChange = (): void => {
  applyRoute(parseHashRoute())
}

const changeReminderPage = (nextPage: number): void => {
  if (nextPage < 1 || nextPage > reminderTotalPages.value) return
  reminderPage.value = nextPage
  void fetchReminderList()
}

watch(
  () => props.shopId,
  () => {
    reminderPage.value = 1
    void fetchRuleList()
    void fetchReminderCount()
    if (currentView.value === 'reminders') {
      void fetchReminderList()
    }
  },
  { immediate: true }
)

onMounted(() => {
  applyRoute(parseHashRoute())
  window.addEventListener('hashchange', handleHashChange)
})

onUnmounted(() => {
  window.removeEventListener('hashchange', handleHashChange)
})
</script>

<template>
  <div class="rule-page">
    <header class="page-header">
      <h1>履约管理-履约规则</h1>
    </header>

    <NCard class="summary-box" :bordered="false" size="small">
      <NFlex class="summary-content" justify="space-between" align="center">
        <div class="summary-left">过去24小时内</div>
        <NFlex class="summary-right" vertical align="center">
          <NButton quaternary type="primary" class="summary-number-btn" @click="openReminderView">
            <span class="summary-number">{{ reminderCount }}</span>
          </NButton>
          <div class="summary-label">提醒达人</div>
        </NFlex>
      </NFlex>
    </NCard>

    <NCard class="table-panel" :bordered="false" size="small">
      <div class="table-wrap">
        <NDataTable
          class="rule-data-table"
          :columns="ruleColumns"
          :data="isLoading ? [] : ruleList"
          :loading="isLoading"
          :bordered="false"
          :single-line="false"
          :row-key="(row) => row.id"
          :scroll-x="980"
        >
          <template #empty>
            <div class="table-empty">{{ ruleTableEmptyText }}</div>
          </template>
        </NDataTable>
      </div>
    </NCard>

    <NModal
      :show="isConfigModalVisible"
      :mask-closable="!isConfigSaving"
      :close-on-esc="!isConfigSaving"
      transform-origin="center"
      @update:show="handleConfigModalShowChange"
    >
      <NCard
        v-if="isConfigModalVisible"
        class="config-modal-card"
        :bordered="false"
        content-style="padding: 0; display: flex; flex-direction: column; min-height: 0; overflow: hidden;"
        role="dialog"
        size="small"
      >
        <NFlex class="config-header" justify="space-between" align="center">
          <h2 class="config-title">配置履约规则</h2>
          <NButton quaternary circle class="modal-close-btn" @click="cancelConfig">
            <span class="close-symbol">×</span>
          </NButton>
        </NFlex>

        <div class="config-panel">
          <div class="config-form">
            <section class="config-section">
              <NDescriptions class="config-descriptions" label-placement="left" :column="1" size="small">
                <NDescriptionsItem label="规则名称">{{ configRuleName }}</NDescriptionsItem>
                <NDescriptionsItem label="是否启用">
                  <NSwitch v-model:value="configForm.enabled" size="small" />
                </NDescriptionsItem>
                <NDescriptionsItem label="规则说明">{{ configRuleDescription }}</NDescriptionsItem>
                <NDescriptionsItem label="执行事件">{{ configRuleEvent }}</NDescriptionsItem>
              </NDescriptions>
            </section>

            <section class="config-section">
              <label class="config-field-label" for="fulfillment-rule-message">提醒消息</label>
              <NInput
                id="fulfillment-rule-message"
                v-model:value="configForm.message"
                class="config-textarea"
                type="textarea"
                :autosize="{ minRows: 4, maxRows: 8 }"
                :maxlength="RULE_MESSAGE_MAX_LENGTH"
                show-count
                placeholder="填写需要发送给达人的 message"
              />
              <div class="config-input-hint" :class="{ error: isRuleMessageTooLong }">
                最多 {{ RULE_MESSAGE_MAX_LENGTH }} 字，当前 {{ ruleMessageLength }} 字
              </div>
            </section>
          </div>
        </div>

        <footer class="config-footer">
          <NButton tertiary :disabled="isConfigSaving" @click="cancelConfig">取消</NButton>
          <NButton type="primary" :loading="isConfigSaving" :disabled="isRuleMessageTooLong" @click="saveRuleConfig">确定</NButton>
        </footer>
      </NCard>
    </NModal>

    <NModal
      :show="isReminderModalVisible"
      :mask-closable="true"
      :close-on-esc="true"
      transform-origin="center"
      @update:show="handleReminderModalShowChange"
    >
      <NCard
        v-if="isReminderModalVisible"
        class="reminder-modal-card"
        :bordered="false"
        content-style="padding: 0; display: flex; flex-direction: column; min-height: 0; overflow: hidden;"
        role="dialog"
        size="small"
      >
        <NFlex class="reminder-header" justify="space-between" align="center">
          <NFlex class="reminder-title-wrap" align="baseline" :size="18">
            <span class="reminder-main-title">履约管理</span>
            <span class="reminder-sub-title">提醒记录</span>
          </NFlex>
          <NButton quaternary circle class="modal-close-btn" @click="backToRuleList">
            <span class="close-symbol">×</span>
          </NButton>
        </NFlex>

        <div class="reminder-panel">
          <div class="table-wrap">
            <NDataTable
              class="rule-data-table reminder-data-table"
              :columns="reminderColumns"
              :data="isReminderLoading ? [] : pagedReminders"
              :loading="isReminderLoading"
              :bordered="false"
              :single-line="false"
              :row-key="(row) => row.id"
              :scroll-x="760"
            >
              <template #empty>
                <div class="table-empty">{{ reminderTableEmptyText }}</div>
              </template>
            </NDataTable>
          </div>

          <footer class="pagination-row">
            <span class="total-text">共 {{ reminderTotal }} 条</span>
            <NPagination :page="reminderPage" :page-size="reminderPageSize" :item-count="reminderTotal" @update:page="changeReminderPage" />
          </footer>
        </div>
      </NCard>
    </NModal>
  </div>
</template>

<style scoped>
.rule-page {
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
  margin-bottom: 14px;
}

.page-header h1 {
  margin: 0;
  color: #1f2d3d;
  font-size: 22px;
  font-weight: 700;
}

.summary-box {
  overflow: hidden;
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #fff;
  margin-bottom: 14px;
}

.summary-box :deep(.n-card__content) {
  padding: 16px 32px !important;
}

.summary-content {
  width: 100%;
}

.summary-left {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  color: #3a4a5f;
  font-size: 16px;
  font-weight: 600;
}

.summary-right {
  flex: 1;
  text-align: center;
}

.summary-number {
  font-size: 38px;
  line-height: 1;
  color: #4063c0;
  font-weight: 700;
}

.summary-number-btn {
  height: auto;
  padding: 0;
}

.summary-number-btn:hover .summary-number {
  color: #0f67ff;
}

.summary-label {
  margin-top: 6px;
  color: #5b6d83;
  font-size: 13px;
}

.table-panel,
.config-panel,
.reminder-panel {
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #fff;
}

.table-panel {
  overflow: hidden;
}

.table-panel :deep(.n-card__content) {
  padding: 0 !important;
}

.table-wrap {
  width: 100%;
  overflow-x: auto;
}

.rule-name {
  font-weight: 600;
}

.modal-close-btn {
  color: #6b7b90;
  font-size: 20px;
  --n-color-focus: transparent !important;
}

.modal-close-btn:deep(.n-button__content) {
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-symbol {
  display: block;
  line-height: 1;
  transform: translateY(-1px);
}

.rule-data-table:deep(.n-data-table-th) {
  background: #f8fafc;
  color: #4a5868;
  font-weight: 600;
}

.rule-data-table:deep(.n-data-table-td) {
  color: #2b3a4a;
}

.table-empty {
  padding: 24px 12px;
  text-align: center;
  color: #7d8da1;
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

.pagination-row :deep(.n-pagination) {
  margin-left: auto;
}

.config-panel {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 0;
  border-radius: 0;
  background: #f4f7fb;
  padding: 16px 18px;
}

.reminder-panel {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 12px 16px 18px;
}

.config-modal-card,
.reminder-modal-card {
  width: 720px;
  max-width: calc(100vw - 32px);
  height: min(760px, calc(100vh - 40px));
  max-height: calc(100vh - 40px);
  border-radius: 12px;
  box-shadow: 0 18px 48px rgba(11, 27, 52, 0.35);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.config-modal-card:deep(.n-card__content),
.reminder-modal-card:deep(.n-card__content) {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.config-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #ecf1f7;
  background: #fff;
}

.reminder-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #dbe3ef;
  background: #fff;
}

.config-title {
  margin: 0;
  color: #1f2d3d;
  font-size: 18px;
  font-weight: 700;
}

.reminder-title-wrap {
  display: flex;
  align-items: baseline;
  gap: 18px;
}

.reminder-main-title {
  color: #1f2d3d;
  font-size: 18px;
  font-weight: 700;
}

.reminder-sub-title {
  color: #4a5868;
  font-size: 14px;
}

.config-form {
  padding: 0;
}

.config-section {
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #fff;
  padding: 14px;
  margin-bottom: 12px;
}

.config-descriptions {
  margin-bottom: 0;
}

.config-descriptions :deep(.n-descriptions-table) {
  border-collapse: separate;
  border-spacing: 0 8px;
}

.config-descriptions :deep(.n-descriptions-table-header),
.config-descriptions :deep(.n-descriptions-table-content) {
  font-size: 14px;
  color: #2b3a4a;
  line-height: 1.7;
  padding-top: 2px;
  padding-bottom: 2px;
}

.config-field-label {
  display: block;
  margin-bottom: 10px;
  color: #1f2d3d;
  font-size: 14px;
  font-weight: 700;
}

.config-textarea {
  width: 100%;
  color: #1f2d3d;
  font-size: 14px;
}

.config-textarea:deep(.n-input-wrapper) {
  border-radius: 8px;
}

.config-textarea:deep(textarea) {
  min-height: 112px;
  color: #1f2d3d;
  font-size: 14px;
  resize: vertical;
}

.config-input-hint {
  margin-top: 6px;
  color: #7f8792;
  font-size: 12px;
  line-height: 1.4;
  text-align: right;
}

.config-input-hint.error {
  color: #d03050;
}

.config-visual-panel {
  min-height: 180px;
  margin: 14px 0 18px;
  border-radius: 2px;
  background: #f1f1f1;
}

.config-visual-placeholder {
  min-height: 180px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #7f8792;
  font-size: 13px;
}

.config-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid #ecf1f7;
  padding: 12px 18px;
  background: #fff;
}

.config-footer :deep(.n-button) {
  min-width: 88px;
  border-radius: 8px;
}

.config-footer :deep(.n-button__content) {
  font-size: 14px;
}

.reminder-table {
  min-width: 840px;
}

@media (max-width: 768px) {
  .rule-page {
    padding: 14px;
  }

  .page-header h1 {
    font-size: 18px;
  }

  .summary-number {
    font-size: 30px;
  }

  .summary-box {
    padding: 12px;
  }

  .pagination-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .config-header,
  .reminder-header {
    align-items: flex-start;
    gap: 10px;
  }

  .reminder-title-wrap {
    gap: 10px;
  }

  .config-footer {
    padding-left: 16px;
    padding-right: 16px;
  }
}
</style>
