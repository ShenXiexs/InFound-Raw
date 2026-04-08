<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { fetchCurrentUser } from '../api/user.api'
import { isEmbedModalShell, requestCloseEmbedModalShell } from '../utils/embed-modal-shell'

type SettingsTab = 'profile' | 'permissions' | 'upgrade' | 'contact'

const NAV_ITEMS: { key: SettingsTab | 'password'; label: string; isPassword?: boolean }[] = [
  { key: 'profile', label: '个人信息' },
  { key: 'password', label: '修改密码', isPassword: true },
  { key: 'permissions', label: '我的权限' },
  { key: 'upgrade', label: '升级续费' },
  { key: 'contact', label: '联系客服' }
]

const activeTab = ref<SettingsTab>('profile')
const displayUserName = ref('—')
const displayPhone = ref('—')
const displayUserType = ref('—')
const displayMemberDateRange = ref('—')
const displayMaxShopCount = ref('—')
const displayMaxOutreachCountPerDay = ref('—')
const displayMaxRemindCreatorCountPerDay = ref('—')
const displayEnableExportCreatorData = ref('—')

const EMBED_VERSION = import.meta.env.VITE_APP_VERSION?.trim() || '1.0'
const appVersionText = computed(() => `寻达 v${EMBED_VERSION}`)

const officialSite = computed(() => {
  const u = import.meta.env.VITE_OFFICIAL_WEBSITE_BASE_URL?.trim()
  return u || 'https://www.xunda.club/'
})
const supportEmail = 'support@xunda.club'

const isEmbedModal = computed(() => isEmbedModalShell())

const parseTabFromHash = (): void => {
  const raw = window.location.hash.replace(/^#/, '') || ''
  const qPart = raw.includes('?') ? raw.split('?')[1] : ''
  const params = new URLSearchParams(qPart)
  const q = params.get('tab')
  if (q === 'permissions' || q === 'upgrade' || q === 'contact') {
    activeTab.value = q
    return
  }
  activeTab.value = 'profile'
}

const maskPhone = (raw: string | undefined): string => {
  if (!raw?.trim()) return '—'
  const digits = raw.replace(/\D/g, '')
  const normalizedDigits = digits.startsWith('86') && digits.length >= 13 ? digits.slice(2) : digits
  if (normalizedDigits.length >= 11) {
    return `+86 ${normalizedDigits.slice(0, 3)}*****${normalizedDigits.slice(-2)}`
  }
  if (normalizedDigits.length >= 7) {
    return `${normalizedDigits.slice(0, 3)}****${normalizedDigits.slice(-4)}`
  }
  return raw
}

const formatDateRange = (startDate?: string, endDate?: string): string => {
  const start = startDate?.trim() || ''
  const end = endDate?.trim() || ''
  if (start && end) return `${start} ~ ${end}`
  return start || end || '—'
}

const loadProfile = async (): Promise<void> => {
  const u = await fetchCurrentUser()
  if (u?.username?.trim()) {
    displayUserName.value = u.username.trim()
  }
  displayPhone.value = maskPhone(u?.phoneNumber)
  displayUserType.value = u?.userType?.trim() || '—'
  const permissionDateRange = u?.permission?.availableDateRang || u?.permission?.availabeDateRang
  displayMemberDateRange.value = formatDateRange(permissionDateRange?.startDate, permissionDateRange?.endDate)
  displayMaxShopCount.value = String(u?.permission?.maxShopCount ?? '—')
  displayMaxOutreachCountPerDay.value =
    u?.permission?.maxOutreachCountPerDay == null ? '—' : `${u.permission.maxOutreachCountPerDay}/天`
  displayMaxRemindCreatorCountPerDay.value =
    u?.permission?.maxRemindCreatorCountPerDay == null ? '—' : `${u.permission.maxRemindCreatorCountPerDay}/天`
  displayEnableExportCreatorData.value =
    typeof u?.permission?.enableExportCreatorData === 'boolean' ? (u.permission.enableExportCreatorData ? '已开启' : '未开启') : '—'
}

const onNavClick = (key: SettingsTab | 'password', isPassword?: boolean): void => {
  if (isPassword) {
    window.location.hash = '#/change-password'
    return
  }
  activeTab.value = key as SettingsTab
  window.location.hash = `#/settings?tab=${key}`
}

const onCheckUpdate = (): void => {
  window.alert('检查更新功能开发中')
}

const onOpenAgreement = (): void => {
  window.alert('软件使用协议（占位）')
}

const goBackOutreach = (): void => {
  window.location.hash = '#/outreach'
}

const onHashChange = (): void => {
  parseTabFromHash()
}

onMounted(() => {
  parseTabFromHash()
  void loadProfile()
  window.addEventListener('hashchange', onHashChange)
})

onUnmounted(() => {
  window.removeEventListener('hashchange', onHashChange)
})
</script>

<template>
  <div class="settings-page">
    <aside class="settings-sidebar">
      <h1 class="sidebar-title">设置</h1>
      <nav class="sidebar-nav" aria-label="设置导航">
        <button
          v-for="item in NAV_ITEMS"
          :key="item.key"
          class="nav-item"
          :class="{ active: !item.isPassword && activeTab === item.key }"
          type="button"
          @click="onNavClick(item.key, item.isPassword)"
        >
          {{ item.label }}
        </button>
      </nav>
      <div class="sidebar-footer">
        <span class="version-text">{{ appVersionText }}</span>
        <button class="link-like" type="button" @click="onCheckUpdate">检查更新</button>
      </div>
    </aside>

    <div class="settings-main">
      <button v-if="isEmbedModal" class="modal-close-btn" type="button" @click="requestCloseEmbedModalShell">关闭</button>
      <button v-else class="back-link" type="button" @click="goBackOutreach">返回一键建联</button>

      <section v-if="activeTab === 'profile'" class="panel">
        <h2 class="panel-heading">个人信息</h2>
        <div class="info-card">
          <div class="info-row">
            <span class="info-label">用户名：</span>
            <span class="info-value">{{ displayUserName }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">电话：</span>
            <span class="info-value">{{ displayPhone }}</span>
          </div>
        </div>
      </section>

      <section v-if="activeTab === 'permissions'" class="panel">
        <h2 class="panel-heading">我的权限</h2>
        <div class="info-card">
          <div class="info-row">
            <span class="info-label">会员等级：</span>
            <span class="info-value">{{ displayUserType }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">会员有效期：</span>
            <span class="info-value">{{ displayMemberDateRange }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">店铺支持：</span>
            <span class="info-value">{{ displayMaxShopCount }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">建联达人数：</span>
            <span class="info-value">{{ displayMaxOutreachCountPerDay }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">履约提醒人次：</span>
            <span class="info-value">{{ displayMaxRemindCreatorCountPerDay }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">导出达人数据：</span>
            <span class="info-value">{{ displayEnableExportCreatorData }}</span>
          </div>
        </div>
      </section>

      <section v-if="activeTab === 'upgrade'" class="panel">
        <h2 class="panel-heading">升级/续费</h2>
        <div class="info-card upgrade-card">
          <p class="upgrade-tip">如需升级/付费，请联系我们的客服</p>
          <div class="upgrade-columns">
            <div class="upgrade-col">
              <span class="upgrade-col-title">微信客服</span>
              <div class="qr-placeholder" aria-hidden="true" />
            </div>
            <div class="upgrade-col">
              <span class="upgrade-col-title">whatsapp客服</span>
              <div class="qr-placeholder" aria-hidden="true" />
            </div>
            <div class="upgrade-col">
              <span class="upgrade-col-title">给我们发邮件</span>
              <p class="upgrade-email-hint">{{ supportEmail }}</p>
            </div>
          </div>
        </div>
      </section>

      <section v-if="activeTab === 'contact'" class="panel">
        <h2 class="panel-heading">联系客服</h2>
        <div class="info-card">
          <div class="info-row block">
            <span class="info-label">官方网站：</span>
            <a :href="officialSite" class="info-link" rel="noreferrer" target="_blank">{{ officialSite }}</a>
          </div>
          <div class="info-row block">
            <span class="info-label">客服邮箱：</span>
            <a :href="`mailto:${supportEmail}`" class="info-link">{{ supportEmail }}</a>
          </div>
        </div>
        <button class="agreement-link" type="button" @click="onOpenAgreement">软件使用协议</button>
      </section>
    </div>
  </div>
</template>

<style lang="scss" scoped>
.settings-page {
  display: flex;
  min-height: 100vh;
  height: 100vh;
  background: #ffffff;
  box-sizing: border-box;
}

.settings-sidebar {
  width: 240px;
  flex-shrink: 0;
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  padding: 24px 16px 20px;
  box-sizing: border-box;
}

.sidebar-title {
  margin: 0 0 20px 4px;
  font-size: 22px;
  font-weight: 700;
  color: #111827;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.nav-item {
  text-align: left;
  padding: 10px 12px;
  border: none;
  border-radius: 8px;
  background: transparent;
  font-size: 14px;
  color: #374151;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: #f3f4f6;
  }

  &.active {
    background: #eff6ff;
    color: #0f67ff;
    font-weight: 600;
  }
}

.sidebar-footer {
  margin-top: auto;
  padding-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.version-text {
  font-size: 12px;
  color: #9ca3af;
}

.link-like {
  align-self: flex-start;
  padding: 0;
  border: none;
  background: none;
  font-size: 13px;
  color: #0f67ff;
  cursor: pointer;

  &:hover {
    text-decoration: underline;
  }
}

.settings-main {
  flex: 1;
  position: relative;
  padding: 20px 28px 32px;
  min-width: 0;
}

.back-link {
  display: inline-block;
  margin-bottom: 16px;
  padding: 0;
  border: none;
  background: none;
  font-size: 13px;
  color: #0f67ff;
  cursor: pointer;

  &:hover {
    text-decoration: underline;
  }
}

.modal-close-btn {
  position: absolute;
  top: 20px;
  right: 28px;
  padding: 6px 16px;
  border-radius: 8px;
  border: 1px solid #d1d5db;
  background: #ffffff;
  font-size: 14px;
  font-weight: 500;
  color: #111827;
  cursor: pointer;

  &:hover {
    background: #f3f4f6;
    border-color: #9ca3af;
  }
}

.panel {
  & + & {
    margin-top: 28px;
  }
}

.panel-heading {
  margin: 0 0 14px;
  min-height: 36px;
  display: flex;
  align-items: center;
  padding-right: 96px;
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}

.info-card {
  background: #f5f5f5;
  border-radius: 10px;
  padding: 20px 22px;
  max-width: 640px;
}

.info-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 14px;
  line-height: 1.6;

  & + & {
    margin-top: 12px;
  }

  &.block {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }
}

.info-label {
  color: #4b5563;
  flex-shrink: 0;
}

.info-value {
  color: #111827;
}

.info-link {
  color: #0f67ff;
  word-break: break-all;

  &:hover {
    text-decoration: underline;
  }
}

.upgrade-card {
  max-width: 900px;
}

.upgrade-tip {
  margin: 0 0 20px;
  font-size: 14px;
  color: #374151;
}

.upgrade-columns {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}

.upgrade-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
}

.upgrade-col-title {
  font-size: 14px;
  color: #374151;
}

.qr-placeholder {
  width: 120px;
  height: 120px;
  background: #d1d5db;
  border-radius: 8px;
}

.upgrade-email-hint {
  margin: 0;
  font-size: 13px;
  color: #6b7280;
  word-break: break-all;
}

.agreement-link {
  margin-top: 16px;
  padding: 0;
  border: none;
  background: none;
  font-size: 14px;
  color: #0f67ff;
  cursor: pointer;

  &:hover {
    text-decoration: underline;
  }
}

@media (max-width: 900px) {
  .upgrade-columns {
    grid-template-columns: 1fr;
  }
}
</style>
