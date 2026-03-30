<script lang="ts" setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { dateZhCN, zhCN } from 'naive-ui'
import { RendererState, rendererStore } from '@renderer/store/renderer-store'
import ButtonGroupOfTitleBar from '@renderer/components/ButtonGroupOfTitleBar.vue'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { TkShopSetting } from '@common/types/tk-type'
import { TAB_TYPES } from '@common/app-constants'
import { resolveResourceAssetUrl } from '@renderer/utils/asset-url'
import { Tab } from '@common/types/tab-type'
import { commonThemeOverrides } from '@infound/desktop-base'

const globalState: RendererState = rendererStore.currentState
const icon = computed(() => resolveResourceAssetUrl(globalState.appSetting.resourcesPath, 'icons/common/icon.png'))
const shopName = ref('寻达')

const tabs = ref<Tab[]>([])
const activeId = ref<string>('') // 当前激活标签ID
const address = ref('')
const canGoBack = ref(false)
const canGoForward = ref(false)

// 左右滚动按钮禁用状态
const scrollLeftDisabled = ref(true)
const scrollRightDisabled = ref(true)

// 监听标签更新
const handleTabsUpdated = (data: { activeId: string; tabs: Tab[] }): void => {
  tabs.value = data.tabs
  activeId.value = data.activeId || (data.tabs.length > 0 ? data.tabs[0].id : '')
  const active = data.tabs.find((t) => t.id === activeId.value)

  address.value = '寻达内部处理页' //暂定

  if (active && active.type != TAB_TYPES.XUNDA) {
    address.value = active.url
  }

  // 更新滚动按钮状态
  nextTick(() => updateScrollButtons())
  // 自动滚动激活标签到可视区
  if (activeId.value) {
    const el = document.querySelector(`.tab[data-id="${activeId.value}"]`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
    }
  }
}

// 监听导航状态
const handleNavState = (data: { canGoBack: boolean; canGoForward: boolean }): void => {
  canGoBack.value = data.canGoBack
  canGoForward.value = data.canGoForward
}

// 标签激活
const handleTabClick = async (id: string): Promise<void> => {
  window.logger.debug('标签点击:', id)
  await window.ipc.invoke(IPC_CHANNELS.TABS_ACTIVATE_ITEM, id)
}

//关闭标签页
const handleClose = async (id: string): Promise<void> => {
  window.logger.debug('关闭标签:', id)
  await window.ipc.invoke(IPC_CHANNELS.TABS_CLOSE_ITEM, id)
}

// 导航操作
const goBack = async (): Promise<void> => await window.ipc.invoke(IPC_CHANNELS.TABS_NAVIGATE_BACK)
const goForward = async (): Promise<void> => await window.ipc.invoke(IPC_CHANNELS.TABS_NAVIGATE_FORWARD)
const reload = async (): Promise<void> => await window.ipc.invoke(IPC_CHANNELS.TABS_NAVIGATE_RELOAD)

// 下拉菜单
const showTabsMenu = async (event: MouseEvent): Promise<void> => {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  await window.ipc.invoke(IPC_CHANNELS.TABS_SHOW_ITEMS_MENU, rect.left, rect.bottom)
}

// 拖拽排序
const dragSourceId = ref<string | null>(null)

const handleDragStart = (e: DragEvent, id: string): void => {
  if (e.dataTransfer == null) return
  e.dataTransfer.setData('text/plain', id)
  e.dataTransfer.effectAllowed = 'move'
  dragSourceId.value = id
}

const handleDragOver = (e: DragEvent): void => {
  e.preventDefault()
  e.dataTransfer!.dropEffect = 'move'
}

const handleDrop = async (e: DragEvent, targetId: string): Promise<void> => {
  e.preventDefault()
  const sourceId = dragSourceId.value
  if (!sourceId || sourceId === targetId) return

  const currentIds = tabs.value.map((t) => t.id)
  const sourceIndex = currentIds.indexOf(sourceId)
  const targetIndex = currentIds.indexOf(targetId)
  if (sourceIndex === -1 || targetIndex === -1) return

  const newOrder = [...currentIds]
  newOrder.splice(sourceIndex, 1)
  newOrder.splice(targetIndex, 0, sourceId)

  // 发送重新排序请求到主进程
  await window.ipc.invoke(IPC_CHANNELS.TABS_REORDER_ITEMS, newOrder)
}
// 左右滚动逻辑
const tabListRef = ref<HTMLElement | null>(null)
const scrollLeft = (): void => {
  if (tabListRef.value) {
    tabListRef.value.scrollBy({ left: -200, behavior: 'smooth' })
    setTimeout(updateScrollButtons, 300)
  }
}
const scrollRight = (): void => {
  if (tabListRef.value) {
    tabListRef.value.scrollBy({ left: 200, behavior: 'smooth' })
    setTimeout(updateScrollButtons, 300)
  }
}

const updateScrollButtons = (): void => {
  const el = tabListRef.value
  if (!el) return
  const { scrollLeft, scrollWidth, clientWidth } = el
  scrollLeftDisabled.value = scrollLeft <= 1
  scrollRightDisabled.value = scrollLeft + clientWidth >= scrollWidth - 1
}

// 标题截断
const MAX_TITLE_LENGTH = 15 //todo:暂定为15个字
const truncatedTitle = (title: string): string => {
  return title.length > MAX_TITLE_LENGTH ? title.substring(0, MAX_TITLE_LENGTH) + '…' : title
}

// 取消监听函数
let offTabs: (() => void) | undefined
let offNav: (() => void) | undefined

onMounted(async () => {
  // 注册 IPC 监听
  offTabs = window.ipc.on(IPC_CHANNELS.RENDERER_MONITOR_TABS_UPDATED, handleTabsUpdated)
  offNav = window.ipc.on(IPC_CHANNELS.RENDERER_MONITOR_TABS_NAVIGATION_STATE, handleNavState)

  // 窗口大小变化时更新滚动按钮
  window.addEventListener('resize', updateScrollButtons)

  shopName.value = '寻达'
  // 尝试获取商铺信息，但不要阻塞后续逻辑
  try {
    const result = await window.ipc.invoke(IPC_CHANNELS.TK_SHOP_GET_TKSHOP_SETTING, globalState.windowId)
    if (result?.success) {
      console.log('Get shop setting:', result)
      const tkShopSetting = result.data as TkShopSetting
      shopName.value = tkShopSetting?.name
    }
  } catch (error) {
    console.error('获取商铺信息失败，使用默认名称', error)
  }
})

onUnmounted(() => {
  offTabs?.()
  offNav?.()
  window.removeEventListener('resize', updateScrollButtons)
})
</script>

<template>
  <n-config-provider :date-locale="dateZhCN" :locale="zhCN" :theme="null" :theme-overrides="commonThemeOverrides">
    <n-global-style />
    <n-message-provider>
      <n-layout class="app-container">
        <!-- 第一行：标题栏（应用图标 + 店铺名称 + 标签控件 + 窗口控制） -->
        <n-layout-header class="header">
          <div class="header-left">
            <n-avatar :size="32" :src="icon" class="title-icon" style="background-color: transparent" />
            <n-ellipsis style="width: 120px">
              <span class="header-title">{{ shopName }}</span>
            </n-ellipsis>
          </div>
          <div class="header-center">
            <div class="header-center-inner">
              <!-- 下拉菜单按钮 -->
              <n-button circle quaternary title="切换标签页" @click="showTabsMenu">
                <template #icon>
                  <n-icon>
                    <i-hugeicons-circle-arrow-down-01 />
                  </n-icon>
                </template>
              </n-button>
              <!-- 左滚动按钮 -->
              <n-button :disabled="scrollLeftDisabled" circle quaternary title="向左滚动" @click="scrollLeft">
                <template #icon>
                  <n-icon>
                    <i-hugeicons-arrow-left-01 />
                  </n-icon>
                </template>
              </n-button>
              <!-- 标签列表容器 -->
              <div ref="tabListRef" class="tab-list" @scroll="updateScrollButtons">
                <div
                  v-for="tab in tabs"
                  :key="tab.id"
                  :class="{ active: tab.id === activeId }"
                  :data-id="tab.id"
                  class="tab"
                  draggable="true"
                  @click="handleTabClick(tab.id)"
                  @dragover="handleDragOver"
                  @dragstart="handleDragStart($event, tab.id)"
                  @drop="handleDrop($event, tab.id)"
                >
                  <img v-if="tab.favicon" :alt="tab.title" :src="tab.favicon" class="favicon" />
                  <span :title="tab.title" class="tab-title">{{ truncatedTitle(tab.title) }}</span>
                  <span class="close" @click.stop="handleClose(tab.id)">×</span>
                </div>
              </div>
              <!-- 右滚动按钮 -->
              <n-button :disabled="scrollRightDisabled" circle quaternary title="向右滚动" @click="scrollRight">
                <template #icon>
                  <n-icon>
                    <i-hugeicons-arrow-right-01 />
                  </n-icon>
                </template>
              </n-button>
            </div>
          </div>
          <div class="header-right">
            <button-group-of-title-bar />
          </div>
        </n-layout-header>
        <!-- 第二行：导航栏（后退/前进/刷新 + 地址栏 + 业务按钮） -->
        <n-layout-header class="nav-row">
          <div class="nav-left">
            <n-button :disabled="!canGoBack" circle quaternary title="后退" @click="goBack">
              <template #icon>
                <n-icon>
                  <i-hugeicons-arrow-left-02 />
                </n-icon>
              </template>
            </n-button>
            <n-button :disabled="!canGoForward" circle quaternary title="前进" @click="goForward">
              <template #icon>
                <n-icon>
                  <i-hugeicons-arrow-right-02 />
                </n-icon>
              </template>
            </n-button>
            <n-button circle quaternary title="刷新" @click="reload">
              <template #icon>
                <n-icon>
                  <i-hugeicons-refresh-04 />
                </n-icon>
              </template>
            </n-button>
          </div>
          <div class="nav-center">
            <n-input id="urlAddress" v-model:value="address" disabled placeholder="" />
          </div>
          <div class="nav-right">
            <n-button text>
              <div class="icon-text-btn">
                <n-icon><i-hugeicons-connect /></n-icon>
                <span class="btn-text">一键建联</span>
              </div>
            </n-button>
            <n-button text>
              <div class="icon-text-btn">
                <n-icon><i-hugeicons-target-01 /></n-icon>
                <span class="btn-text">履约管理</span>
              </div>
            </n-button>
            <n-button text>
              <div class="icon-text-btn">
                <n-icon><i-hugeicons-user-group /></n-icon>
                <span class="btn-text">我的达人库</span>
              </div>
            </n-button>
          </div>
        </n-layout-header>
        <!-- 第三行：内容区 -->
        <n-layout-content class="content-area">
          <n-flex align="center" justify="center" style="width: 100%; height: calc(100vh - 99px)">
            <n-result status="418" title="页面加载中..."></n-result>
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
}

/* 标签列表区域 */
.tab-list {
  display: flex;
  flex: 1;
  overflow-x: hidden;
  align-items: center;
  margin: 0 3px;
  height: 100%;
  white-space: nowrap;
  gap: 2px;
  scrollbar-width: none;
  &::-webkit-scrollbar {
    display: none;
  }
}

.tab {
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
  height: 38px;
  background: #e0e0e0;
  border: 1px solid #ccc;
  border-bottom: none;
  border-radius: 5px 5px 0 0;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  flex-shrink: 0;
  margin-right: 3px;
  &:hover {
    background: #d0d0d0;
  }
  &.active {
    background: #f9f9f9;
    font-weight: bold;
    height: 42px;
  }
  .favicon {
    width: 16px;
    height: 16px;
    margin-right: 4px;
  }
  .tab-title {
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .close {
    width: 16px;
    height: 16px;
    line-height: 16px;
    text-align: center;
    border-radius: 50%;
    background: transparent;
    color: #666;
    cursor: pointer;
    font-size: 14px;
    margin-left: 4px;
    &:hover {
      background: rgba(0, 0, 0, 0.2);
      color: #333;
    }
  }
}

/* 第二行导航栏 */
.nav-row {
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  background: #f9f9f9;
  border-bottom: 1px solid #aaa;
  flex-shrink: 0;

  .nav-left {
    display: flex;
    align-items: center;
    gap: 5px;
    flex-shrink: 0;
  }
  .nav-center {
    flex: 1;
    padding: 0 12px;
    min-width: 0;
  }
  .nav-center :deep(.n-input.n-input--disabled) {
    --n-text-color: #767c82 !important;
    --n-color-disabled: white !important;
  }
  .nav-center :deep(.n-input.n-input--disabled .n-input__input-el) {
    cursor: text !important;
  }
  .nav-center :deep(.n-input) {
    cursor: text !important;
  }
  .nav-right {
    display: flex;
    align-items: center;
    gap: 0 10px;
    margin-left: 12px;
    flex-shrink: 0;

    .icon-text-btn {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 6px;
    }

    .btn-text {
      font-size: 12px;
      white-space: nowrap;
    }
  }
}

/* 内容区 */
.content-area {
  flex: 1;
  background: transparent;
}
</style>
