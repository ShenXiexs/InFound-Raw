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
  window.logger.info('开始启动 RPA 调试会话')
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
            <span class="header-title">寻达 RPA 调试器</span>
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
            <n-button type="primary" @click="startRPASimulation">启动调试会话</n-button>
            <n-alert type="info" title="当前定位">
              <code>frontend.desktop</code> 才是 seller RPA 的正式宿主。这里仅保留 Playwright 执行引擎与本地调试能力。
              启动调试会话只会拉起一组待命运行时，不代表正式任务入口。
            </n-alert>
            <n-alert type="warning" title="登录态说明">
              正式任务优先使用 <code>input.session.loginState</code> 注入登录态；本地调试仍可使用
              <code>loginStatePath</code> 或手动登录。默认区域仍为 MX。
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
