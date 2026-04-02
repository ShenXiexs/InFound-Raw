<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { dateZhCN, zhCN } from 'naive-ui'
import { AppReleaseInfo, commonThemeOverrides } from '@infound/desktop-base'
import { RendererState, rendererStore } from '@renderer/store/renderer-store'
import { IPC_CHANNELS } from '@common/types/ipc-type'

const globalState: RendererState = rendererStore.currentState

const appReleaseInfo = ref<AppReleaseInfo>({
  needUpdate: false,
  version: '',
  releaseDate: '',
  releaseNotes: ''
})

const isDownloading = ref(false)
const percentage = ref(0)
const formattedReleaseNotes = computed(() => {
  return appReleaseInfo.value.releaseNotes.replaceAll('\n', '<br />')
})

const onExitAppToUpgrade = (): void => {
  window.ipc.invoke(IPC_CHANNELS.APP_UPDATE_DOWNLOAD, globalState.windowId, 'afterExit').then((res) => {
    if (res.success) {
      isDownloading.value = false
      window.ipc.send(IPC_CHANNELS.APP_UPDATE_CLOSE)
    }
  })
}

const onUpgradeNow = (): void => {
  window.ipc.on(IPC_CHANNELS.RENDERER_MONITOR_APP_UPDATE_PROGRESS, (speed, percent) => {
    window.logger.debug(`APP_UPDATE_PROGRESS: ${speed}, ${percent}`)
    percentage.value = percent
  })
  window.ipc.invoke(IPC_CHANNELS.APP_UPDATE_DOWNLOAD, globalState.windowId, 'immediately').then((res) => {
    if (res.success) {
      isDownloading.value = true
    }
  })
}

onMounted(() => {
  window.ipc.invoke(IPC_CHANNELS.APP_UPDATE_INFO).then((res) => {
    if (res.success) {
      appReleaseInfo.value = res.data!
    }
  })
})
</script>

<template>
  <n-config-provider :date-locale="dateZhCN" :locale="zhCN" :theme="null" :theme-overrides="commonThemeOverrides">
    <n-global-style />
    <n-message-provider>
      <n-flex align="center" justify="center" style="height: 100vh; width: 100%; padding: 0" vertical>
        <n-icon-wrapper :border-radius="50" :size="80">
          <n-icon size="60px">
            <i-hugeicons-rocket-01 />
          </n-icon>
        </n-icon-wrapper>
        <n-text style="text-align: center; font-size: 18px; padding: 15px" type="success">
          升级「寻达」<br />
          v {{ appReleaseInfo!.version }}
        </n-text>
        <div style="width: 400px">
          <n-progress v-if="isDownloading" :percentage="percentage" indicator-placement="inside" type="line" />
          <n-card v-else>
            <n-scrollbar style="height: 80px; width: 100%" trigger="none">
              <n-p>
                <span v-html="formattedReleaseNotes"></span>
              </n-p>
            </n-scrollbar>
          </n-card>
        </div>
        <n-space justify="space-around" style="margin-top: 20px">
          <n-button :disabled="isDownloading" style="width: 150px" type="default" @click="onExitAppToUpgrade">稍后更新</n-button>
          <n-button :disabled="isDownloading" style="width: 150px" type="primary" @click="onUpgradeNow">立即更新</n-button>
        </n-space>
      </n-flex>
    </n-message-provider>
  </n-config-provider>
</template>
