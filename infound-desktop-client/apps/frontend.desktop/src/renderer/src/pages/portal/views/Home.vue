<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { rendererStore } from '@renderer/store/renderer-store'

const router = useRouter()
const message = useMessage()
const isLoggingOut = ref(false)
const isLoadingApiInfo = ref(false)
const currentUserApiResult = ref<Record<string, any> | null>(null)
const checkTokenApiResult = ref<Record<string, any> | null>(null)
const deviceId = computed(() => rendererStore.currentState.appInfo.deviceId || '')

const addTkShop = (): void => {
  window.logger.info('添加店铺')
  window.ipc.send(IPC_CHANNELS.TK_SHOP_OPEN_WINDOW, 'abc')
}

const fetchAndPrintApiInfo = async (): Promise<void> => {
  if (isLoadingApiInfo.value) return

  isLoadingApiInfo.value = true
  try {
    const [currentUserResult, checkTokenResult] = await Promise.all([
      window.ipc.invoke(IPC_CHANNELS.APP_AUTH_GET_CURRENT_USER),
      window.ipc.invoke(IPC_CHANNELS.APP_AUTH_CHECK_TOKEN)
    ])

    if (!currentUserResult.success) {
      message.error(currentUserResult.error || '获取用户信息失败')
    }
    if (!checkTokenResult.success) {
      message.error(checkTokenResult.error || '校验 token 失败')
    }

    currentUserApiResult.value = currentUserResult.data || null
    checkTokenApiResult.value = checkTokenResult.data || null

    window.logger.info('主页打印 /user/current 返回', currentUserResult)
    window.logger.info('主页打印 /user/check-token 返回', checkTokenResult)
  } catch (error) {
    window.logger.error('主页获取接口信息失败', error)
    message.error('获取接口信息失败，请稍后重试')
  } finally {
    isLoadingApiInfo.value = false
  }
}

const logout = async (): Promise<void> => {
  if (isLoggingOut.value) return

  isLoggingOut.value = true
  try {
    const result = await window.ipc.invoke(IPC_CHANNELS.APP_AUTH_LOGOUT)
    if (!result.success) {
      message.error(result.error || '退出登录失败，请稍后重试')
      return
    }

    rendererStore.currentState.currentUser = undefined
    rendererStore.currentState.isLogin = false
    rendererStore.currentState.enableDebug = false

    message.success('已退出登录')
    await router.replace('/login')
  } catch (error) {
    window.logger.error('退出登录失败', error)
    message.error('退出登录失败，请稍后重试')
  } finally {
    isLoggingOut.value = false
  }
}

onMounted(() => {
  window.logger.info('主页打印 deviceId', deviceId.value)
  void fetchAndPrintApiInfo()
})
</script>

<template>
  <div class="home-page">
    <div class="toolbar">
      <n-button type="default" :loading="isLoadingApiInfo" @click="fetchAndPrintApiInfo">打印接口返回</n-button>
      <n-button type="default" secondary :loading="isLoggingOut" @click="logout">退出登录</n-button>
    </div>
    <h1>主页</h1>
    <n-card title="Device ID" size="small" class="result-card">
      <pre class="result-pre">{{ deviceId || '(empty)' }}</pre>
    </n-card>
    <n-button type="primary" @click="addTkShop">添加店铺</n-button>
    <n-card title="/user/current" size="small" class="result-card">
      <pre class="result-pre">{{ JSON.stringify(currentUserApiResult, null, 2) }}</pre>
    </n-card>
    <n-card title="/user/check-token" size="small" class="result-card">
      <pre class="result-pre">{{ JSON.stringify(checkTokenApiResult, null, 2) }}</pre>
    </n-card>
  </div>
</template>

<style lang="scss" scoped>
.home-page {
  padding: 20px;
}

.toolbar {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-bottom: 12px;
}

.result-card {
  margin-top: 12px;
}

.result-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
