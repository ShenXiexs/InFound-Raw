<script lang="ts" setup>
import { computed, reactive } from 'vue'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { rendererStore } from '@renderer/store/renderer-store'
import { AppState } from '@infound/desktop-shared'
import { resolveResourceAssetUrl } from '@renderer/utils/asset-url'

const globalState: AppState = rendererStore.currentState
const logo = computed(() => {
  const url = resolveResourceAssetUrl(globalState.appSetting.resourcesPath, 'logo.png')
  if (url) return url
  return `${globalState.appSetting.resourcesPath}/logo.png`
})
const version = globalState.appInfo.version

const progressModel = reactive({
  percent: 0,
  status: '启动中...'
})

window.ipc.on(IPC_CHANNELS.RENDERER_MONITOR_APP_SPLASH_WINDOW_STATE_SYNC, (data: { percent: number; status: string }) => {
  progressModel.percent = data.percent
  progressModel.status = data.status
})
</script>

<template>
  <n-config-provider :theme="null">
    <n-global-style />
    <n-message-provider>
      <n-flex align="center" justify="center" style="height: 100vh; width: 100%; padding: 16px" vertical>
        <img :src="logo" alt="Xunda Logo" style="height: 160px; width: auto; object-fit: contain" />
        <n-h2>v{{ version }}</n-h2>
        <n-text>{{ progressModel.status }}</n-text>
        <n-progress
          :percentage="progressModel.percent"
          :show-indicator="true"
          style="width: 420px; max-width: 90vw; margin-top: 8px"
          type="line"
          :processing="true"
          color="#18a058"
          rail-color="#e5e7eb"
        />
      </n-flex>
    </n-message-provider>
  </n-config-provider>
</template>

<style lang="scss" scoped></style>
