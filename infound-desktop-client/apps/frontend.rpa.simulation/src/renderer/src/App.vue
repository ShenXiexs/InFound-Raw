<script lang="ts" setup>
import { ref } from 'vue'
import { darkTheme, dateZhCN, zhCN } from 'naive-ui'
import { IPC_CHANNELS } from '@common/types/ipc-type'

const isMaximized = ref(false)

const onMinimize = (): void => {
  window.ipc.send(IPC_CHANNELS.APP_MINIMIZED)
}

const onMaximize = async (): Promise<void> => {
  const result = await window.ipc.invoke(IPC_CHANNELS.APP_MAXIMIZED)
  if (result.success) {
    isMaximized.value = result.isMaximized
  }
}

const onClose = (): void => {
  window.ipc.send(IPC_CHANNELS.APP_CLOSED)
}

const onOpenDevTools = (): void => {
  window.ipc.send(IPC_CHANNELS.APP_OPEN_WINDOW_DEV_TOOLS, 'undocked')
}

const onOpenSubDevTools = (): void => {
  window.ipc.send(IPC_CHANNELS.APP_OPEN_SUB_WINDOW_DEV_TOOLS, 'undocked')
}

const loginRPA = (): void => {
  window.logger.info('开始登录店铺')
  window.ipc.send(IPC_CHANNELS.RPA_SELLER_LOGIN)
}

const startRPASimulation = (): void => {
  window.logger.info('开始启动 RPA 模拟会话')
  window.ipc.send(IPC_CHANNELS.RPA_EXECUTE_SIMULATION)
}
</script>

<template>
  <n-config-provider :date-locale="dateZhCN" :locale="zhCN" :theme="darkTheme" :theme-overrides="{ common: { fontWeightStrong: '600' } }">
    <n-global-style />
    <n-message-provider>
      <n-layout>
        <n-layout-header class="header">
          <div class="header-left">
            <span class="header-title">寻达 RPA 模拟器</span>
          </div>
          <div class="header-right">
            <n-button :focusable="false" circle quaternary @click="onOpenDevTools">
              <template #icon>
                <n-icon>
                  <i-hugeicons-code-simple />
                </n-icon>
              </template>
            </n-button>
            <n-button :focusable="false" circle quaternary @click="onOpenSubDevTools">
              <template #icon>
                <n-icon>
                  <i-hugeicons-source-code />
                </n-icon>
              </template>
            </n-button>
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
          </div>
        </n-layout-header>
        <n-layout-content>
          <n-flex vertical style="padding: 20px; gap: 16px">
            <n-button @click="loginRPA">登录店铺</n-button>
            <n-button type="primary" @click="startRPASimulation">启动RPA模拟</n-button>
            <n-alert type="info" title="当前执行模型">
              登录店铺只负责准备登录态。启动RPA模拟只会启动一个 Playwright 会话并停留在 affiliate 首页待命，不会自动执行任何机器人。
              如果没有 storage-state，Playwright 会直接打开登录页等待手动操作。会话启动后，再通过特定任务指令投送建联、样品管理、聊天机器人或达人详情。
            </n-alert>
          </n-flex>
        </n-layout-content>
      </n-layout>
    </n-message-provider>
  </n-config-provider>
</template>

<style lang="scss" scoped>
.header {
  -webkit-app-region: drag;
  height: 40px;
  padding: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e5e7eb;
  z-index: 10;

  .header-left {
    display: flex;
    align-items: center;
    gap: 8px;

    .header-title {
      font-size: 18px;
      font-weight: 600;
    }
  }

  .header-right {
    -webkit-app-region: no-drag;
    display: flex;
    align-items: center;
    gap: 16px;
  }
}
</style>
