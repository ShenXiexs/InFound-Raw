<script lang="ts" setup>
import { computed, reactive } from 'vue'
import { AppState, commonThemeOverrides } from '@infound/desktop-base'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { rendererStore } from '@renderer/store/renderer-store'
import { resolveResourceAssetUrl } from '@renderer/utils/asset-url'

const globalState: AppState = rendererStore.currentState
const logo = computed(() => {
  const url = resolveResourceAssetUrl(globalState.appSetting.resourcesPath, 'icons/common/logo2.png')
  if (url) return url
  return `${globalState.appSetting.resourcesPath}/icons/common/logo2.png`
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
  <n-config-provider :theme="null" :theme-overrides="commonThemeOverrides">
    <n-global-style />
    <n-message-provider>
      <n-flex align="center" justify="center" style="height: 100vh; width: 100%; padding: 0" vertical>
        <n-image :src="logo" height="160" preview-disabled style="margin-top: 30px" />
        <n-h2>v{{ version }}</n-h2>
        <n-text>{{ progressModel.status }}</n-text>
        <n-progress
          :percentage="progressModel.percent"
          :processing="true"
          :show-indicator="true"
          color="#8142f6"
          rail-color="#e5e7eb"
          style="width: 420px; max-width: 90vw; margin-top: 8px"
          type="line"
        />
      </n-flex>
    </n-message-provider>
  </n-config-provider>
</template>
