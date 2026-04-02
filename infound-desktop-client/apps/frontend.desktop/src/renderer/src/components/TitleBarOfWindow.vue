<script lang="ts" setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { DropdownOption } from 'naive-ui'
import { useMessage } from 'naive-ui'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { RendererState, rendererStore } from '@renderer/store/renderer-store'
import ButtonGroupOfTitleBar from '@renderer/components/ButtonGroupOfTitleBar.vue'
import { resolveResourceAssetUrl } from '@renderer/utils/asset-url'

const globalState: RendererState = rendererStore.currentState
const icon = computed(() => resolveResourceAssetUrl(globalState.appSetting.resourcesPath, 'icons/common/icon.png'))
const router = useRouter()
const message = useMessage()

const displayUserName = computed(() => {
  return globalState.currentUser?.username?.trim() || '未登录用户'
})

const showUserActions = computed(() => {
  return Boolean(globalState.isLogin && globalState.currentUser?.username?.trim())
})

const userAvatarText = computed(() => {
  return displayUserName.value.slice(0, 1).toUpperCase()
})

const onClickUpgrade = (): void => {
  message.info('升级套餐功能开发中')
}

const userMenuOptions: DropdownOption[] = [
  { label: '个人信息', key: 'profile' },
  { label: '会员权限', key: 'membership' },
  { label: '退出登录', key: 'logout' }
]

const forceBackToLogin = async (): Promise<void> => {
  try {
    await window.ipc.invoke(IPC_CHANNELS.API_AUTH_LOGOUT)
  } catch {
    // 忽略登出接口失败，继续清理本地状态并跳转登录
  }

  globalState.currentUser = undefined
  globalState.isLogin = false
  globalState.enableDebug = false

  if (router.currentRoute.value.path !== '/login') {
    await router.replace({ path: '/login', query: { needLogin: '1' } })
  }
}

const onSelectUserMenu = async (key: string | number): Promise<void> => {
  if (key === 'logout') {
    await forceBackToLogin()
    return
  }

  message.info('功能开发中')
}
</script>

<template>
  <n-layout-header class="header">
    <div class="header-left">
      <n-avatar :size="32" :src="icon" class="title-icon" style="background-color: transparent" />
      <span class="header-title">寻达</span>
    </div>
    <div class="header-right">
      <div v-if="showUserActions" class="user-actions">
        <n-button class="upgrade-btn" size="small" text @click="onClickUpgrade">
          <template #icon>
            <n-icon size="14">
              <svg fill="none" viewBox="0 0 24 24">
                <path d="M8 8V7.5C8 5.567 9.567 4 11.5 4H12.5C14.433 4 16 5.567 16 7.5V8" stroke="currentColor" stroke-linecap="round" stroke-width="1.8" />
                <path
                  d="M5.5 8.5H18.5C19.88 8.5 21 9.62 21 11V17.5C21 18.88 19.88 20 18.5 20H5.5C4.12 20 3 18.88 3 17.5V11C3 9.62 4.12 8.5 5.5 8.5Z"
                  stroke="currentColor"
                  stroke-width="1.8"
                />
              </svg>
            </n-icon>
          </template>
          升级套餐
        </n-button>
        <n-dropdown v-if="globalState.isLogin" :options="userMenuOptions" trigger="click" @select="onSelectUserMenu">
          <div class="user-menu-trigger">
            <n-avatar :size="30" class="user-avatar" round>{{ userAvatarText }}</n-avatar>
            <span class="user-name ellipsis-1">{{ displayUserName }}</span>
          </div>
        </n-dropdown>
      </div>
      <button-group-of-title-bar />
    </div>
  </n-layout-header>
</template>

<style lang="scss" scoped>
@use '@renderer/assets/styles/title-bar.scss' as *;

.title-icon :deep(img) {
  object-fit: contain;
}

.user-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-name {
  font-size: 13px;
  color: #374151;
  max-width: 140px;
}

.ellipsis-1 {
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.user-avatar {
  background: linear-gradient(135deg, #f59e0b, #f97316);
  color: #ffffff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.user-avatar :deep(.n-avatar__text) {
  line-height: 1;
}

.upgrade-btn {
  height: 28px;
  border-radius: 14px;
  padding: 0 12px;
  margin-right: 8px;
}

.user-menu-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 220px;
  min-width: 0;
  cursor: pointer;
  user-select: none;
}
</style>
