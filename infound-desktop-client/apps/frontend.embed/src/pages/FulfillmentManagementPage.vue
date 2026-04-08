<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { createDiscreteApi, NButton, NCard, NInput, NModal, NSwitch } from 'naive-ui'
import {
  getFulfillmentReminderLast24hCount,
  getFulfillmentReminderRecordList,
  getFulfillmentRuleList,
  setFulfillmentRuleEnabled,
  updateFulfillmentRule,
  type FulfillmentRuleItem as ApiFulfillmentRuleItem
} from '../api/fulfillment.api'

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

const { message } = createDiscreteApi(['message'])

const reminderCount = ref(0)
const page = ref(1)
const pageSize = 8
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

const total = computed(() => ruleList.value.length)
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const pagedRules = computed(() => {
  const start = (page.value - 1) * pageSize
  return ruleList.value.slice(start, start + pageSize)
})
const pageNumbers = computed(() => Array.from({ length: totalPages.value }, (_, index) => index + 1))
const reminderTotal = ref(0)
const reminderTotalPages = computed(() => Math.max(1, Math.ceil(reminderTotal.value / reminderPageSize)))
const pagedReminders = computed(() => reminderList.value)
const reminderPageNumbers = computed(() => Array.from({ length: reminderTotalPages.value }, (_, index) => index + 1))
const activeRule = computed(() => ruleList.value.find((item) => item.id === activeRuleId.value) || null)
const configRuleName = computed(() => activeRule.value?.ruleName || activeRule.value?.ruleCode || '-')
const configRuleDescription = computed(() => activeRule.value?.ruleDescription || '-')
const configRuleEvent = computed(() => activeRule.value?.ruleEvent || '-')
const ruleMessageLength = computed(() => configForm.message.length)
const isRuleMessageTooLong = computed(() => ruleMessageLength.value > RULE_MESSAGE_MAX_LENGTH)
const isConfigModalVisible = computed(() => currentView.value === 'config')
const isReminderModalVisible = computed(() => currentView.value === 'reminders')
const isRuleToggling = (ruleId: string): boolean => togglingRuleIds.value.includes(ruleId)

watch(totalPages, (value) => {
  if (page.value > value) {
    page.value = value
  }
})

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
    sentAt: toDisplayText(item.remindAt ?? item.sentAt ?? item.sendTime ?? item.createdAt ?? item.created_at)
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

const changePage = (nextPage: number): void => {
  if (nextPage < 1 || nextPage > totalPages.value) return
  page.value = nextPage
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
    page.value = 1
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

    <section class="summary-box">
      <div class="summary-left">过去24小时内</div>
      <div class="summary-right">
        <button class="summary-number-btn" type="button" @click="openReminderView">
          <span class="summary-number">{{ reminderCount }}</span>
        </button>
        <div class="summary-label">提醒达人</div>
      </div>
    </section>

    <section class="table-panel">
      <div class="table-wrap">
        <table class="rule-table">
          <thead>
            <tr>
              <th>规则名称</th>
              <th>规则说明</th>
              <th>规则事件</th>
              <th class="nowrap-column">是否启用</th>
              <th class="nowrap-column">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="isLoading">
              <td class="empty-row" colspan="5">加载中...</td>
            </tr>
            <tr v-else-if="errorMessage">
              <td class="empty-row" colspan="5">{{ errorMessage }}</td>
            </tr>
            <tr v-for="item in pagedRules" :key="item.id">
              <td class="rule-name">{{ item.ruleName }}</td>
              <td>{{ item.ruleDescription }}</td>
              <td>{{ item.ruleEvent }}</td>
              <td class="nowrap-column">
                <div class="switch-cell">
                  <span>{{ item.enabled ? '已启用' : '未启用' }}</span>
                  <button
                    :class="['switch-btn', { on: item.enabled }]"
                    :disabled="isRuleToggling(item.id)"
                    :title="
                      isRuleToggling(item.id)
                        ? '请求中...'
                        : item.enabled
                          ? '关闭规则'
                          : item.canEnable
                            ? '启用规则'
                            : '当前不可启用'
                    "
                    type="button"
                    @click="toggleRule(item.id)"
                  >
                    <span class="switch-thumb" />
                  </button>
                </div>
              </td>
              <td class="nowrap-column">
                <button class="config-btn" :title="item.configured ? '配置' : '未配置'" type="button" @click="configureRule(item.id)">
                  <span aria-hidden="true">✎</span>
                  <span>{{ item.configured ? '配置' : '待配置' }}</span>
                </button>
              </td>
            </tr>
            <tr v-if="!isLoading && !errorMessage && pagedRules.length === 0">
              <td class="empty-row" colspan="5">暂无履约规则</td>
            </tr>
          </tbody>
        </table>
      </div>

      <footer class="pagination-row">
        <span class="total-text">共 {{ total }} 条</span>
        <div class="pager">
          <button :disabled="page <= 1" type="button" @click="changePage(page - 1)">上一页</button>
          <button
            v-for="item in pageNumbers"
            :key="item"
            :class="{ active: item === page }"
            type="button"
            @click="changePage(item)"
          >
            {{ item }}
          </button>
          <button :disabled="page >= totalPages" type="button" @click="changePage(page + 1)">下一页</button>
        </div>
      </footer>
    </section>

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
        <header class="config-header">
          <div class="config-title-wrap">
            <span class="config-breadcrumb">履约管理 &gt; 配置履约规则</span>
          </div>
          <button class="modal-close-btn" type="button" @click="cancelConfig">×</button>
        </header>

        <div class="config-panel">
          <div class="config-form">
            <div class="config-row">
              <span class="config-label">规则名称:</span>
              <span class="config-text">{{ configRuleName }}</span>
            </div>

            <div class="config-row">
              <span class="config-label">是否启用</span>
              <NSwitch v-model:value="configForm.enabled" size="small" />
            </div>

            <div class="config-row">
              <span class="config-label">规则说明:</span>
              <span class="config-text">{{ configRuleDescription }}</span>
            </div>

            <div class="config-field">
              <span class="config-label">执行事件:</span>
              <span class="config-text">{{ configRuleEvent }}</span>
            </div>

            <div class="config-field">
              <label class="config-label" for="fulfillment-rule-message">提醒消息:</label>
              <div class="config-input-wrap">
                <NInput
                  id="fulfillment-rule-message"
                  v-model:value="configForm.message"
                  type="textarea"
                  :autosize="{ minRows: 3, maxRows: 4 }"
                  :maxlength="RULE_MESSAGE_MAX_LENGTH"
                  show-count
                  placeholder="填写需要发送给达人的 message"
                />
                <div class="config-input-hint" :class="{ error: isRuleMessageTooLong }">
                  最多 {{ RULE_MESSAGE_MAX_LENGTH }} 字，当前 {{ ruleMessageLength }} 字
                </div>
              </div>
            </div>

            <div class="config-actions">
              <NButton type="primary" :loading="isConfigSaving" :disabled="isRuleMessageTooLong" @click="saveRuleConfig">确定</NButton>
              <NButton tertiary :disabled="isConfigSaving" @click="cancelConfig">取消</NButton>
            </div>
          </div>
        </div>
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
        <header class="reminder-header">
          <div class="reminder-title-wrap">
            <span class="reminder-main-title">履约管理</span>
            <span class="reminder-sub-title">提醒记录</span>
          </div>
          <button class="modal-close-btn" type="button" @click="backToRuleList">×</button>
        </header>

        <div class="reminder-panel">
          <div class="table-wrap">
            <table class="rule-table reminder-table">
              <thead>
                <tr>
                  <th>达人</th>
                  <th>粉丝数量</th>
                  <th>GMV</th>
                  <th>命中规则</th>
                  <th>发送提醒时间</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="isReminderLoading">
                  <td class="empty-row" colspan="5">加载中...</td>
                </tr>
                <tr v-else-if="reminderErrorMessage">
                  <td class="empty-row" colspan="5">{{ reminderErrorMessage }}</td>
                </tr>
                <tr v-for="item in pagedReminders" :key="item.id">
                  <td>{{ item.creatorName }}</td>
                  <td>{{ item.followerCount }}</td>
                  <td>{{ item.gmv }}</td>
                  <td>{{ item.matchedRule }}</td>
                  <td>{{ item.sentAt }}</td>
                </tr>
                <tr v-if="!isReminderLoading && !reminderErrorMessage && pagedReminders.length === 0">
                  <td class="empty-row" colspan="5">暂无提醒记录</td>
                </tr>
              </tbody>
            </table>
          </div>

          <footer class="pagination-row">
            <span class="total-text">共 {{ reminderTotal }} 条</span>
            <div class="pager">
              <button :disabled="reminderPage <= 1" type="button" @click="changeReminderPage(reminderPage - 1)">上一页</button>
              <button
                v-for="item in reminderPageNumbers"
                :key="item"
                :class="{ active: item === reminderPage }"
                type="button"
                @click="changeReminderPage(item)"
              >
                {{ item }}
              </button>
              <button :disabled="reminderPage >= reminderTotalPages" type="button" @click="changeReminderPage(reminderPage + 1)">下一页</button>
            </div>
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
  display: grid;
  grid-template-columns: 1fr 1fr;
  align-items: center;
  border: 1px solid #dbe3ef;
  border-radius: 10px;
  background: #fff;
  padding: 16px 32px;
  margin-bottom: 14px;
}

.summary-left {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #3a4a5f;
  font-size: 16px;
  font-weight: 600;
}

.summary-right {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.summary-number {
  font-size: 38px;
  line-height: 1;
  color: #4063c0;
  font-weight: 700;
}

.summary-number-btn {
  border: 0;
  background: transparent;
  padding: 0;
  cursor: pointer;
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

.table-wrap {
  width: 100%;
  overflow-x: auto;
}

.rule-table {
  width: 100%;
  border-collapse: collapse;
  min-width: 980px;
}

.rule-table th,
.rule-table td {
  text-align: left;
  padding: 12px 14px;
  border-bottom: 1px solid #ecf1f7;
  font-size: 14px;
  color: #2b3a4a;
}

.rule-table th {
  font-weight: 600;
  color: #4a5868;
  background: #f8fafc;
}

.rule-name {
  font-weight: 600;
}

.nowrap-column {
  white-space: nowrap;
  width: 1%;
}

.switch-cell {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.switch-btn {
  width: 42px;
  height: 24px;
  border: 1px solid #d0d9e6;
  border-radius: 999px;
  background: #e7edf8;
  cursor: pointer;
  padding: 1px;
  display: inline-flex;
  align-items: center;
  transition: all 0.2s ease;
}

.switch-btn.on {
  background: #0f67ff;
  border-color: #0f67ff;
  justify-content: flex-end;
}

.switch-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.switch-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(18, 29, 46, 0.25);
}

.config-btn,
.config-back {
  border: 0;
  background: transparent;
  color: #0f67ff;
  cursor: pointer;
  padding: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
}

.modal-close-btn {
  border: 0;
  background: transparent;
  font-size: 22px;
  line-height: 1;
  color: #6b7b90;
  cursor: pointer;
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
  gap: 6px;
}

.pager button {
  min-width: 30px;
  height: 30px;
  border: 1px solid #d0d9e6;
  border-radius: 6px;
  background: #fff;
  color: #2b3a4a;
  cursor: pointer;
  padding: 0 8px;
}

.pager button.active {
  border-color: #0f67ff;
  color: #0f67ff;
  background: #eef5ff;
}

.pager button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.config-panel {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 12px 16px 24px;
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
  border-bottom: 1px solid #dbe3ef;
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

.config-breadcrumb {
  color: #2b3a4a;
  font-size: 14px;
}

.config-title-wrap {
  display: flex;
  align-items: center;
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
  padding: 16px 8px 0;
}

.config-row,
.config-field {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.config-label {
  width: 72px;
  flex: 0 0 72px;
  color: #2b3a4a;
  font-size: 13px;
  line-height: 32px;
}

.config-text {
  color: #2b3a4a;
  font-size: 13px;
  line-height: 32px;
}

.config-field :deep(.n-input) {
  max-width: 520px;
}

.config-input-wrap {
  width: 100%;
  max-width: 520px;
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

.config-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
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

  .pagination-row,
  .config-row,
  .config-field {
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

  .config-label {
    width: auto;
    flex-basis: auto;
    line-height: 1.5;
  }
}
</style>
