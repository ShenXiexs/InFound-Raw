<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { NConfigProvider, type GlobalThemeOverrides } from 'naive-ui'
import OutreachTaskManagementPage from './pages/OutreachTaskManagementPage.vue'
import FulfillmentManagementPage from './pages/FulfillmentManagementPage.vue'
import SettingsPage from './pages/SettingsPage.vue'
import ChangePasswordPage from './pages/ChangePasswordPage.vue'
import { type EmbedNetworkLogEntry, subscribeNetworkLog } from './debug/network-log'
import { initEmbedModalShellFromUrl } from './utils/embed-modal-shell'

/** 须在子页面挂载前执行（父 onMounted 晚于子组件挂载） */
initEmbedModalShellFromUrl()

type EmbedPage = 'outreach' | 'fulfillment' | 'settings' | 'changePassword'
const SHOP_ID_QUERY_PARAM = 'shopId'
const SHOP_ID_STORAGE_KEY = 'xunda-shop-id'
const PAGE_TITLES: Record<EmbedPage, string> = {
  outreach: '一键建联',
  fulfillment: '履约管理',
  settings: '设置',
  changePassword: '修改密码'
}
const DOCUMENT_TITLE_SUFFIX = ' - 寻达'

const currentPage = ref<EmbedPage>('outreach')
const shopId = ref('')
/** 仅本地 dev 构建（`vite --mode dev`）；stg/pro 构建与 `dev:stg` 等均不展示 */
const isNetworkPanelEnabled = import.meta.env.MODE === 'dev'
const isNetworkPanelCollapsed = ref(false)
const networkLogs = ref<EmbedNetworkLogEntry[]>([])
let unsubscribeNetworkLog: (() => void) | undefined

const embedThemeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#0f67ff',
    primaryColorHover: '#2a78ff',
    primaryColorPressed: '#0d5ce3',
    primaryColorSuppl: '#0f67ff',
    infoColor: '#0f67ff',
    infoColorHover: '#2a78ff',
    infoColorPressed: '#0d5ce3',
    infoColorSuppl: '#0f67ff'
  }
}

const resolvePageByHash = (): EmbedPage => {
  const hash = window.location.hash.toLowerCase()
  if (hash.includes('/change-password')) {
    return 'changePassword'
  }
  if (hash.includes('/settings')) {
    return 'settings'
  }
  if (hash.includes('/fulfillment')) {
    return 'fulfillment'
  }
  return 'outreach'
}

const syncPageByHash = (): void => {
  currentPage.value = resolvePageByHash()
}

const syncDocumentTitle = (): void => {
  document.title = `${PAGE_TITLES[currentPage.value]}${DOCUMENT_TITLE_SUFFIX}`
}

const getStoredShopId = (): string => {
  try {
    return window.localStorage.getItem(SHOP_ID_STORAGE_KEY)?.trim() || window.sessionStorage.getItem(SHOP_ID_STORAGE_KEY)?.trim() || ''
  } catch (_error) {
    return ''
  }
}

const persistShopId = (value: string): void => {
  const normalizedValue = value.trim()
  if (!normalizedValue) return
  try {
    window.localStorage.setItem(SHOP_ID_STORAGE_KEY, normalizedValue)
    window.sessionStorage.setItem(SHOP_ID_STORAGE_KEY, normalizedValue)
  } catch (_error) {
    // ignore storage errors in restricted contexts
  }
}

const syncShopId = (): void => {
  const url = new URL(window.location.href)
  const queryShopId = url.searchParams.get(SHOP_ID_QUERY_PARAM)?.trim() || ''
  shopId.value = queryShopId || getStoredShopId()
  if (queryShopId) {
    persistShopId(queryShopId)
  }
}

const syncShopIdFromDesktop = async (): Promise<void> => {
  if (shopId.value) return

  const invoke = (window as any).ipc?.invoke as ((channel: string, ...args: any[]) => Promise<any>) | undefined
  if (typeof invoke !== 'function') return

  try {
    const windowId = await invoke('app-get-window-id')
    const result = await invoke('tk-shop-get-tk-shop-setting', windowId)
    const id = result?.data?.id
    if (typeof id === 'string' && id.trim()) {
      shopId.value = id.trim()
      persistShopId(shopId.value)
    }
  } catch (_error) {
    // ignore
  }
}

const currentComponent = computed(() => {
  switch (currentPage.value) {
    case 'fulfillment':
      return FulfillmentManagementPage
    case 'settings':
      return SettingsPage
    case 'changePassword':
      return ChangePasswordPage
    default:
      return OutreachTaskManagementPage
  }
})

const isPlainWhitePage = computed(() => currentPage.value === 'settings' || currentPage.value === 'changePassword')

const embedChildProps = computed((): Record<string, string> => {
  if (currentPage.value === 'outreach' || currentPage.value === 'fulfillment') {
    return { shopId: shopId.value }
  }
  return {}
})

const appendNetworkLog = (entry: EmbedNetworkLogEntry): void => {
  networkLogs.value = [entry, ...networkLogs.value].slice(0, 200)
}

const clearNetworkLogs = (): void => {
  networkLogs.value = []
}

const toggleNetworkPanel = (): void => {
  isNetworkPanelCollapsed.value = !isNetworkPanelCollapsed.value
}

const formatPayload = (payload: Record<string, any>): string => {
  try {
    return JSON.stringify(payload, null, 2)
  } catch (_error) {
    return String(payload)
  }
}

onMounted(() => {
  syncPageByHash()
  syncDocumentTitle()
  syncShopId()
  void syncShopIdFromDesktop()
  if (isNetworkPanelEnabled) {
    unsubscribeNetworkLog = subscribeNetworkLog(appendNetworkLog)
  }
  window.addEventListener('hashchange', syncPageByHash)
})

watch(currentPage, () => {
  syncDocumentTitle()
})

onUnmounted(() => {
  unsubscribeNetworkLog?.()
  window.removeEventListener('hashchange', syncPageByHash)
})
</script>

<template>
  <div :class="['embed-shell', { 'is-plain-white': isPlainWhitePage }]">
    <div :class="['embed-frame', { 'is-plain-white': isPlainWhitePage }]">
      <NConfigProvider :theme="null" :theme-overrides="embedThemeOverrides">
        <component :is="currentComponent" v-bind="embedChildProps" />
      </NConfigProvider>
    </div>

    <aside v-if="isNetworkPanelEnabled" :class="['network-debug-panel', { collapsed: isNetworkPanelCollapsed }]">
      <header class="panel-header">
        <span class="panel-title">网络日志 ({{ networkLogs.length }})</span>
        <div class="panel-actions">
          <button class="panel-btn" type="button" @click="toggleNetworkPanel">
            {{ isNetworkPanelCollapsed ? '展开' : '收起' }}
          </button>
          <button class="panel-btn danger" type="button" @click="clearNetworkLogs">清空</button>
        </div>
      </header>
      <div v-if="!isNetworkPanelCollapsed" class="panel-body">
        <div v-if="networkLogs.length === 0" class="panel-empty">暂无日志</div>
        <article v-for="item in networkLogs" :key="item.id" :class="['log-item', item.level]">
          <div class="log-head">
            <span class="log-time">{{ item.time }}</span>
            <span class="log-level">{{ item.level.toUpperCase() }}</span>
            <span class="log-message">{{ item.message }}</span>
          </div>
          <pre class="log-payload">{{ formatPayload(item.payload) }}</pre>
        </article>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.embed-shell {
  min-height: 100vh;
  background: #f3f5fb;
  position: relative;
}

.embed-shell.is-plain-white {
  background: #ffffff;
}

.embed-frame {
  min-height: 100vh;
}

.embed-frame.is-plain-white {
  background: #ffffff;
}

.network-debug-panel {
  position: fixed;
  right: 12px;
  bottom: 12px;
  width: min(520px, calc(100vw - 24px));
  max-height: 52vh;
  border: 1px solid #d2dbec;
  border-radius: 10px;
  background: #ffffff;
  box-shadow: 0 8px 28px rgba(23, 35, 56, 0.2);
  z-index: 9999;
  overflow: hidden;
}

.network-debug-panel.collapsed {
  max-height: none;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-bottom: 1px solid #e7edf7;
  background: #f7f9fd;
}

.panel-title {
  font-size: 13px;
  color: #1c2b40;
  font-weight: 700;
}

.panel-actions {
  display: flex;
  gap: 8px;
}

.panel-btn {
  border: 1px solid #ccd7ea;
  background: #fff;
  color: #2e3d53;
  border-radius: 6px;
  padding: 2px 8px;
  cursor: pointer;
  font-size: 12px;
}

.panel-btn.danger {
  color: #9a1f2d;
  border-color: #e3b8bf;
}

.panel-body {
  overflow: auto;
  max-height: calc(52vh - 42px);
  padding: 8px;
}

.panel-empty {
  color: #64748b;
  font-size: 12px;
  padding: 8px;
}

.log-item {
  border: 1px solid #dde5f3;
  border-radius: 8px;
  background: #fafcff;
  padding: 8px;
  margin-bottom: 8px;
}

.log-item.error {
  border-color: #f2cad0;
  background: #fff6f8;
}

.log-head {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.log-time {
  color: #607089;
  font-size: 12px;
}

.log-level {
  font-size: 11px;
  font-weight: 700;
  color: #243247;
  background: #e8eefb;
  border-radius: 10px;
  padding: 1px 6px;
}

.log-item.error .log-level {
  color: #8d1f2b;
  background: #f7dde1;
}

.log-message {
  color: #1f2d3d;
  font-size: 12px;
}

.log-payload {
  margin: 0;
  border-radius: 6px;
  background: #f2f6fc;
  color: #23344b;
  padding: 8px;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
