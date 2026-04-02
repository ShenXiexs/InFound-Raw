<script lang="ts" setup>
import { ref } from 'vue'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { RendererState, rendererStore } from '@renderer/store/renderer-store'

const globalState: RendererState = rendererStore.currentState
const isMaximized = ref(false)

const onMinimize = (): void => {
  window.ipc.send(IPC_CHANNELS.APP_MINIMIZED, globalState.windowId)
}

const onMaximize = async (): Promise<void> => {
  const result = await window.ipc.invoke(IPC_CHANNELS.APP_MAXIMIZED, globalState.windowId)
  if (result.success) {
    isMaximized.value = result.isMaximized
  }
}

const onClose = (): void => {
  window.ipc.send(IPC_CHANNELS.APP_CLOSED, globalState.windowId)
}

const onOpenDevTools = (): void => {
  window.ipc.send(IPC_CHANNELS.APP_OPEN_WINDOW_DEV_TOOLS, globalState.windowId, 'undocked')
}

/*const onOpenSubDevTools = (): void => {
  window.ipc.send(IPC_CHANNELS.APP_OPEN_SUB_WINDOW_DEV_TOOLS, globalState.windowId, 'undocked')
}*/
</script>

<template>
  <n-button v-if="globalState.enableDebug" :focusable="false" circle quaternary @click="onOpenDevTools">
    <template #icon>
      <n-icon>
        <i-hugeicons-code-simple />
      </n-icon>
    </template>
  </n-button>
  <!--  <n-button :focusable="false" circle quaternary @click="onOpenSubDevTools">
    <template #icon>
      <n-icon>
        <i-hugeicons-source-code />
      </n-icon>
    </template>
  </n-button>-->
  <n-button :focusable="false" circle quaternary @click="onMinimize">
    <template #icon>
      <n-icon>
        <i-hugeicons-minus-sign />
      </n-icon>
    </template>
  </n-button>
  <n-button :focusable="false" circle quaternary @click="onMaximize">
    <template #icon>
      <n-icon>
        <i-hugeicons-full-screen v-if="!isMaximized" />
        <i-hugeicons-arrow-shrink v-if="isMaximized" />
      </n-icon>
    </template>
  </n-button>
  <n-button :focusable="false" circle quaternary @click="onClose">
    <template #icon>
      <n-icon>
        <i-hugeicons-cancel-01 />
      </n-icon>
    </template>
  </n-button>
</template>
