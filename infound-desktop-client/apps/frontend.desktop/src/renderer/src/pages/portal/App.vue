<script lang="ts" setup>
import { onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { dateZhCN, zhCN } from 'naive-ui'
import TitleBarOfWindow from '@renderer/components/TitleBarOfWindow.vue'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { rendererStore } from '@renderer/store/renderer-store'
import { commonThemeOverrides } from '@infound/desktop-base'

const CHECK_TOKEN_INTERVAL_MS = 60 * 60 * 1000
const TOKEN_INVALID_CODE = 1251

const router = useRouter()
let checkTokenTimer: ReturnType<typeof setInterval> | null = null
let isCheckingToken = false

const hasValidLocalSession = (): boolean => {
  const token = rendererStore.currentState.currentUser?.tokenValue?.trim()
  return Boolean(rendererStore.currentState.isLogin && token)
}

const forceBackToLogin = async (): Promise<void> => {
  try {
    await window.ipc.invoke(IPC_CHANNELS.API_AUTH_LOGOUT)
  } catch {
    // 无论登出接口是否成功，都继续清空本地状态并跳登录
  }

  rendererStore.currentState.currentUser = undefined
  rendererStore.currentState.isLogin = false
  rendererStore.currentState.enableDebug = false

  if (router.currentRoute.value.path !== '/login') {
    await router.replace({ path: '/login', query: { needLogin: '1' } })
  }
}

const checkTokenOnce = async (): Promise<void> => {
  if (isCheckingToken || !hasValidLocalSession()) return

  isCheckingToken = true
  try {
    const result = await window.ipc.invoke(IPC_CHANNELS.API_AUTH_CHECK_TOKEN)
    if (!result.success && result.code === TOKEN_INVALID_CODE) {
      await forceBackToLogin()
    }
  } catch {
    // 定时校验失败不打断页面流程，下一轮继续重试
  } finally {
    isCheckingToken = false
  }
}

onMounted(() => {
  void checkTokenOnce()
  checkTokenTimer = setInterval(() => {
    void checkTokenOnce()
  }, CHECK_TOKEN_INTERVAL_MS)
})

onBeforeUnmount(() => {
  if (checkTokenTimer) {
    clearInterval(checkTokenTimer)
    checkTokenTimer = null
  }
})
</script>

<template>
  <n-config-provider :date-locale="dateZhCN" :locale="zhCN" :theme="null" :theme-overrides="commonThemeOverrides">
    <n-global-style />
    <n-message-provider>
      <n-layout class="portal-layout">
        <title-bar-of-window />
        <n-layout-content class="portal-content">
          <RouterView v-slot="{ Component }">
            <component :is="Component" />
          </RouterView>
        </n-layout-content>
      </n-layout>
    </n-message-provider>
  </n-config-provider>
</template>

<style lang="scss" scoped>
.portal-layout {
  height: 100vh;
}

.portal-content {
  height: calc(100vh - 45px);
  overflow-y: auto;
}
</style>
