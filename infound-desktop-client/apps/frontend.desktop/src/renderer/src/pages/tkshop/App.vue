<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import { dateZhCN, zhCN } from 'naive-ui'
import { RendererState, rendererStore } from '@renderer/store/renderer-store'
import ButtonGroupOfTitleBar from '@renderer/components/ButtonGroupOfTitleBar.vue'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { TkShopSetting } from '@common/types/tk-type'
import { resolveResourceAssetUrl } from '@renderer/utils/asset-url'

const globalState: RendererState = rendererStore.currentState
const icon = computed(() => resolveResourceAssetUrl(globalState.appSetting.resourcesPath, 'icon.png'))

const shopName = ref('寻达')

onMounted(async () => {
  const result = await window.ipc.invoke(IPC_CHANNELS.TK_SHOP_GET_TKSHOP_SETTING, globalState.windowId)
  window.logger.info(`window id: ${JSON.stringify(result)}`)

  if (result && result.success) {
    const tkShopSetting = result.data as TkShopSetting
    if (tkShopSetting) {
      shopName.value = tkShopSetting.name
      window.logger.info(`shop name: ${shopName.value}`)
    }
  }
})
</script>

<template>
  <n-config-provider :date-locale="dateZhCN" :locale="zhCN" :theme="null" :theme-overrides="{ common: { fontWeightStrong: '600' } }">
    <n-global-style />
    <n-message-provider>
      <n-layout class="app-container">
        <n-layout-header class="header">
          <div class="header-left">
            <n-avatar :src="icon" size="small" style="background-color: transparent" />
            <span class="header-title">
              <n-ellipsis style="width: 120px">{{ shopName }}</n-ellipsis>
            </span>
          </div>
          <div class="header-center">
            <div class="header-center-inner">
              <n-tabs closable size="small" type="card">
                <n-tab name="幸福"> 寂寞围绕着电视 </n-tab>
                <n-tab name="的"> 垂死坚持 </n-tab>
                <n-tab name="旁边"> 在两点半消失 </n-tab>
              </n-tabs>
            </div>
          </div>
          <div class="header-right">
            <button-group-of-title-bar />
          </div>
        </n-layout-header>
        <n-layout-header class="toolbar">
          <div class="toolbar-left">
            <n-button :focusable="false" circle quaternary>
              <template #icon>
                <n-icon>
                  <i-hugeicons-arrow-left-02 />
                </n-icon>
              </template>
            </n-button>
            <n-button :focusable="false" circle quaternary>
              <template #icon>
                <n-icon>
                  <i-hugeicons-arrow-right-02 />
                </n-icon>
              </template>
            </n-button>
            <n-button :focusable="false" circle quaternary>
              <template #icon>
                <n-icon>
                  <i-hugeicons-refresh-04 />
                </n-icon>
              </template>
            </n-button>
          </div>
          <div class="toolbar-center">
            <n-input placeholder="https://" type="text" />
          </div>
          <div class="toolbar-right">
            <n-button text>
              <div class="icon-text-btn">
                <n-icon>
                  <i-hugeicons-connect />
                </n-icon>
                <span class="btn-text">一键建联</span>
              </div>
            </n-button>
            <n-button text>
              <div class="icon-text-btn">
                <n-icon>
                  <i-hugeicons-target-01 />
                </n-icon>
                <span class="btn-text">履约管理</span>
              </div>
            </n-button>
            <n-button text>
              <div class="icon-text-btn">
                <n-icon>
                  <i-hugeicons-user-group />
                </n-icon>
                <span class="btn-text">我的达人库</span>
              </div>
            </n-button>
          </div>
        </n-layout-header>
        <n-layout-content class="main">
          <n-flex align="center" justify="center" style="width: 100%; height: calc(100vh - 94px)">
            <n-spin size="large">
              <template #icon>
                <n-icon>
                  <i-hugeicons-refresh-01 />
                </n-icon>
              </template>
              <template #description>
                <n-h3>页面加载中...</n-h3>
              </template>
            </n-spin>
          </n-flex>
        </n-layout-content>
      </n-layout>
    </n-message-provider>
  </n-config-provider>
</template>

<style lang="scss" scoped>
@use '@renderer/assets/styles/title-bar.scss' as *;

.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  border: 1px solid #3f85ff;
}

.toolbar {
  height: 45px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  z-index: 10;
  padding: 0 10px;
  flex-shrink: 0;

  .toolbar-left {
    display: flex;
    align-items: center;
    height: 100%;
    padding-right: 10px;
    gap: 5px;
  }

  .toolbar-center {
    display: flex;
    flex: 1;
    align-items: center;
    height: 100%;
    padding-right: 10px;
  }

  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 0 10px;

    /* 核心：垂直排列图标和文本 */
    .icon-text-btn {
      display: flex;
      flex-direction: column; /* 垂直排列 */
      align-items: center; /* 水平居中 */
      justify-content: center; /* 垂直居中 */
      width: 100%;
      height: 100%;
      gap: 6px; /* 图标和文本的间距 */
    }

    /* 文本样式优化 */
    .btn-text {
      font-size: 12px;
      white-space: nowrap; /* 防止文本换行 */
    }
  }
}

.main {
  height: calc(100vh - 94px);
}
</style>
