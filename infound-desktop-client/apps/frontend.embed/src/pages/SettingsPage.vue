<script lang="ts" setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { createDiscreteApi, dateZhCN, NButton, NCard, NDescriptions, NDescriptionsItem, NFlex, NForm, NFormItem, NInput, NTabPane, NTabs, zhCN } from 'naive-ui'
import { changePassword, fetchCurrentUser } from '../api'
import { isEmbedModalShell, requestCloseEmbedModalShell } from '../utils/embed-modal-shell'
import { rendererStore } from '../store/renderer-store.ts'

type SettingsTab = 'profile' | 'password' | 'permissions' | 'upgrade' | 'contact'

const NAV_ITEMS: { key: SettingsTab; label: string }[] = [
  { key: 'profile', label: '个人信息' },
  { key: 'password', label: '修改密码' },
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
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const isSubmitting = ref(false)

const EMBED_VERSION = rendererStore.currentState.appInfo.version || '1.0'
const appVersionText = computed(() => `寻达 v${EMBED_VERSION}`)

const officialSite = computed(() => {
  const u = import.meta.env.VITE_OFFICIAL_WEBSITE_BASE_URL?.trim()
  return u || 'https://www.xunda.club/'
})
const supportEmail = 'support@xunda.club'

const isEmbedModal = computed(() => isEmbedModalShell())

const { message } = createDiscreteApi(['message'], {
  configProviderProps: {
    locale: zhCN,
    dateLocale: dateZhCN
  }
})

const parseTabFromHash = (): void => {
  const raw = window.location.hash.replace(/^#/, '') || ''
  if (raw.includes('/change-password')) {
    activeTab.value = 'password'
    return
  }
  const qPart = raw.includes('?') ? raw.split('?')[1] : ''
  const params = new URLSearchParams(qPart)
  const q = params.get('tab')
  if (q === 'password' || q === 'permissions' || q === 'upgrade' || q === 'contact') {
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

const formatChinaDate = (raw?: string): string => {
  const text = raw?.trim() || ''
  if (!text) return ''

  const parsed = new Date(text)
  if (Number.isNaN(parsed.getTime())) {
    const dateOnlyMatch = text.match(/^(\d{4}-\d{2}-\d{2})/)
    return dateOnlyMatch?.[1] || text
  }

  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
    .format(parsed)
    .replace(/\//g, '-')
}

const formatDateRange = (startDate?: string, endDate?: string): string => {
  const start = formatChinaDate(startDate)
  const end = formatChinaDate(endDate)
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
  displayMaxOutreachCountPerDay.value = u?.permission?.maxOutreachCountPerDay == null ? '—' : `${u.permission.maxOutreachCountPerDay}/天`
  displayMaxRemindCreatorCountPerDay.value = u?.permission?.maxRemindCreatorCountPerDay == null ? '—' : `${u.permission.maxRemindCreatorCountPerDay}/天`
  displayEnableExportCreatorData.value = typeof u?.permission?.enableExportCreatorData === 'boolean' ? (u.permission.enableExportCreatorData ? '已开启' : '未开启') : '—'
}

const onNavClick = (key: SettingsTab): void => {
  activeTab.value = key
  window.location.hash = `#/settings?tab=${key}`
}

const getChangePasswordErrorMessage = (error: any): string => {
  const responseData = error?.response?.data
  const statusCode = Number(responseData?.code ?? error?.response?.status)

  if (statusCode === 422) {
    const details = Array.isArray(responseData?.data?.details) ? responseData.data.details : []
    const detailMessage = details
      .map((item: { msg?: unknown }) => {
        if (typeof item?.msg !== 'string') return ''
        return item.msg.trim().replace(/^Value error,\s*/i, '')
      })
      .filter((text: string) => Boolean(text))
      .join('，')

    if (detailMessage) {
      return detailMessage
    }
  }

  const backendMessage = typeof responseData?.msg === 'string' ? responseData.msg.trim() : ''
  if (backendMessage) {
    return backendMessage
  }

  return error?.message || '密码修改失败'
}

const handleSubmit = async (): Promise<void> => {
  const oldPasswordValue = oldPassword.value.trim()
  const newPasswordValue = newPassword.value.trim()
  const confirmPasswordValue = confirmPassword.value.trim()

  if (!oldPasswordValue) {
    message.warning('请输入原密码')
    return
  }
  if (!newPasswordValue) {
    message.warning('请输入新密码')
    return
  }
  if (!confirmPasswordValue) {
    message.warning('请输入确认新密码')
    return
  }
  if (newPasswordValue !== confirmPasswordValue) {
    message.error('两次输入的新密码不一致')
    return
  }
  if (isSubmitting.value) return

  isSubmitting.value = true
  try {
    await changePassword({
      oldPassword: oldPasswordValue,
      newPassword: newPasswordValue,
      confirmPassword: confirmPasswordValue
    })
    message.success('密码修改成功')
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    activeTab.value = 'profile'
    window.location.hash = '#/settings?tab=profile'
  } catch (error: any) {
    message.error(getChangePasswordErrorMessage(error))
  } finally {
    isSubmitting.value = false
  }
}

const onCheckUpdate = (): void => {
  message.info('检查更新功能开发中')
}

const onOpenAgreement = (): void => {
  message.info('软件使用协议功能开发中')
}

const onOpenOfficialSite = (): void => {
  window.open(officialSite.value, '_blank', 'noopener,noreferrer')
}

const onContactByEmail = (): void => {
  window.location.href = `mailto:${supportEmail}`
}

const goBackOutreach = (): void => {
  window.location.hash = '#/outreach'
}

const handleNavTabChange = (value: string | number): void => {
  const target = String(value) as SettingsTab
  onNavClick(target)
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
    <div v-if="isEmbedModal" aria-hidden="true" class="window-drag-region" />
    <aside class="settings-sidebar">
      <h1 class="sidebar-title">设置</h1>
      <NTabs :value="activeTab" animated class="settings-tabs" placement="left" @update:value="handleNavTabChange">
        <NTabPane v-for="item in NAV_ITEMS" :key="item.key" :name="item.key" :tab="item.label" />
      </NTabs>
      <div class="sidebar-footer">
        <span class="version-text">{{ appVersionText }}</span>
        <NButton class="sidebar-link-btn" text type="primary" @click="onCheckUpdate">检查更新</NButton>
      </div>
    </aside>

    <div class="settings-main">
      <NButton v-if="isEmbedModal" aria-label="关闭" circle class="modal-close-btn" quaternary @click="requestCloseEmbedModalShell"> × </NButton>
      <NButton v-else class="back-link" text type="primary" @click="goBackOutreach">返回一键建联</NButton>

      <section v-if="activeTab === 'profile'" class="panel">
        <h2 class="panel-heading">个人信息</h2>
        <NCard :bordered="false" class="info-card">
          <NDescriptions :column="1" class="settings-descriptions" label-placement="left">
            <NDescriptionsItem label="用户名">{{ displayUserName }}</NDescriptionsItem>
            <NDescriptionsItem label="电话">{{ displayPhone }}</NDescriptionsItem>
          </NDescriptions>
        </NCard>
      </section>

      <section v-if="activeTab === 'password'" class="panel">
        <h2 class="panel-heading">修改密码</h2>
        <NCard :bordered="false" class="password-card">
          <NForm class="password-form" label-placement="left" label-width="120">
            <NFormItem label="用户名">
              <div class="row-static">{{ displayUserName }}</div>
            </NFormItem>
            <NFormItem label="原密码">
              <NInput v-model:value="oldPassword" class="row-input" placeholder="请输入原密码" show-password-on="click" type="password" />
            </NFormItem>
            <NFormItem label="新密码">
              <NInput v-model:value="newPassword" class="row-input" placeholder="请输入新密码" show-password-on="click" type="password" />
            </NFormItem>
            <NFormItem label="确认新密码">
              <NInput v-model:value="confirmPassword" class="row-input" placeholder="请再输入一遍新密码" show-password-on="click" type="password" />
            </NFormItem>
            <NFormItem class="password-submit-item" label=" ">
              <div class="password-submit-row">
                <NButton :loading="isSubmitting" type="primary" @click="handleSubmit">确认修改</NButton>
              </div>
            </NFormItem>
          </NForm>
        </NCard>
      </section>

      <section v-if="activeTab === 'permissions'" class="panel">
        <h2 class="panel-heading">我的权限</h2>
        <NCard :bordered="false" class="info-card">
          <NDescriptions :column="1" class="settings-descriptions" label-placement="left">
            <NDescriptionsItem label="会员等级">{{ displayUserType }}</NDescriptionsItem>
            <NDescriptionsItem label="会员有效期">{{ displayMemberDateRange }}</NDescriptionsItem>
            <NDescriptionsItem label="店铺支持">{{ displayMaxShopCount }}</NDescriptionsItem>
            <NDescriptionsItem label="建联达人数">{{ displayMaxOutreachCountPerDay }}</NDescriptionsItem>
            <NDescriptionsItem label="履约提醒人次">{{ displayMaxRemindCreatorCountPerDay }}</NDescriptionsItem>
            <NDescriptionsItem label="导出达人数据">{{ displayEnableExportCreatorData }}</NDescriptionsItem>
          </NDescriptions>
        </NCard>
      </section>

      <section v-if="activeTab === 'upgrade'" class="panel">
        <h2 class="panel-heading">升级/续费</h2>
        <NCard :bordered="false" class="info-card upgrade-card">
          <p class="upgrade-tip">如需升级/付费，请联系我们的客服</p>
          <NFlex :size="[20, 20]" class="upgrade-columns" justify="space-between">
            <NFlex :size="12" class="upgrade-col" vertical>
              <span class="upgrade-col-title">微信客服</span>
              <div aria-hidden="true" class="qr-placeholder" />
            </NFlex>
            <NFlex :size="12" class="upgrade-col" vertical>
              <span class="upgrade-col-title">whatsapp客服</span>
              <div aria-hidden="true" class="qr-placeholder" />
            </NFlex>
            <NFlex :size="12" class="upgrade-col" vertical>
              <span class="upgrade-col-title">给我们发邮件</span>
              <p class="upgrade-email-hint">{{ supportEmail }}</p>
            </NFlex>
          </NFlex>
        </NCard>
      </section>

      <section v-if="activeTab === 'contact'" class="panel">
        <h2 class="panel-heading">联系客服</h2>
        <NCard :bordered="false" class="info-card">
          <NDescriptions :column="1" class="settings-descriptions" label-placement="left">
            <NDescriptionsItem label="官方网站">
              <NButton class="info-link-btn" text type="primary" @click="onOpenOfficialSite">{{ officialSite }}</NButton>
            </NDescriptionsItem>
            <NDescriptionsItem label="客服邮箱">
              <NButton class="info-link-btn" text type="primary" @click="onContactByEmail">{{ supportEmail }}</NButton>
            </NDescriptionsItem>
          </NDescriptions>
        </NCard>
        <NButton class="agreement-link" text type="primary" @click="onOpenAgreement">软件使用协议</NButton>
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
  position: relative;
}

.window-drag-region {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 24px;
  z-index: 1;
  -webkit-app-region: drag;
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

.settings-tabs {
  flex: 1;
}

.settings-tabs:deep(.n-tabs-nav) {
  width: 100%;
}

.settings-tabs:deep(.n-tabs-nav-scroll-wrapper),
.settings-tabs:deep(.n-tabs-nav-scroll-content) {
  width: 100%;
}

.settings-tabs:deep(.n-tabs-tab-wrapper) {
  width: 100%;
}

.settings-tabs:deep(.n-tabs-tab) {
  justify-content: flex-start;
  width: 100%;
  padding: 10px 12px;
}

.settings-tabs:deep(.n-tabs-pane-wrapper) {
  display: none;
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

.sidebar-link-btn {
  align-self: flex-start;
}

.settings-main {
  flex: 1;
  position: relative;
  padding: 24px 40px 48px;
  min-width: 0;
  overflow-y: auto;
}

.back-link {
  margin-bottom: 16px;
}

.modal-close-btn {
  position: absolute;
  top: 20px;
  right: 28px;
  color: #6b7b90;
  font-size: 18px;
  z-index: 2;
  -webkit-app-region: no-drag;
}

.panel {
  max-width: 960px;
}

.panel-heading {
  margin: 0 0 16px;
  min-height: 32px;
  display: flex;
  align-items: center;
  padding-right: 96px;
  font-size: 16px;
  font-weight: 600;
  color: #111827;
}

.info-card {
  max-width: 640px;
  box-shadow: none;
  --n-color: #f5f5f5;
  border-radius: 10px;
}

.info-card:deep(.n-card__content) {
  padding: 24px 24px;
  background: #f5f5f5;
  border-radius: 10px;
}

.password-card {
  max-width: 980px;
  box-shadow: none;
  --n-color: #ffffff;
  border-radius: 10px;
}

.password-card:deep(.n-card__content) {
  padding: 24px 0;
  background: #ffffff;
  border-radius: 10px;
}

.settings-descriptions:deep(.n-descriptions-table-header),
.settings-descriptions:deep(.n-descriptions-table-content) {
  font-size: 14px;
  line-height: 1.6;
}

.settings-descriptions:deep(.n-descriptions-table-header) {
  color: #4b5563;
  width: 120px;
}

.settings-descriptions:deep(.n-descriptions-table-content) {
  color: #111827;
}

.password-form {
  max-width: 920px;
}

.row-static {
  min-height: 34px;
  display: flex;
  align-items: center;
  font-size: 14px;
  color: #111827;
}

.row-input {
  width: 100%;
  max-width: 760px;
}

.password-submit-row {
  width: 100%;
  display: flex;
  justify-content: flex-end;
}

:deep(.password-form .n-form-item) {
  --n-label-text-color: #111827;
}

:deep(.password-form .n-form-item-label) {
  justify-content: flex-start;
  padding-right: 24px;
  font-size: 14px;
}

:deep(.password-form .n-form-item-label__text) {
  width: 100%;
  text-align: left;
}

:deep(.password-submit-item .n-form-item-blank) {
  width: 100%;
}

.info-link-btn {
  word-break: break-all;
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
  width: 100%;
}

.upgrade-col {
  flex: 1;
  min-width: 180px;
  align-items: center;
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
}

@media (max-width: 640px) {
  .settings-main {
    padding: 24px 20px 36px;
  }

  .upgrade-columns {
    flex-direction: column;
  }
}
</style>
