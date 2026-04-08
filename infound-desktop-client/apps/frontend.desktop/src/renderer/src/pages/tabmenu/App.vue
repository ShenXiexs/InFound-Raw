<script lang="ts" setup>
import { ref } from 'vue'
import { dateZhCN, zhCN } from 'naive-ui'
import { commonThemeOverrides } from '@infound/desktop-base'
import { Tab } from '@common/types/tab-type'
import { IPC_CHANNELS } from '@common/types/ipc-type'

// 声明全局变量类型
declare global {
  interface Window {
    initTabs?: (activeId: string, tabs: Tab[]) => void
  }
}

let currentTabs: Tab[] = []
let currentActiveId = ''
const allTabs = ref<Tab[]>([])
const searchKeyword = ref('')
const dragSourceId = ref<string | null>(null)

const filterTabs = (query: string): void => {
  query = query.trim().toLowerCase()
  if (!query) {
    return
  }
  allTabs.value = currentTabs.filter((tab) => (tab.title && tab.title.toLowerCase().includes(query)) || (tab.url && tab.url.toLowerCase().includes(query)))
}

const handleDragStart = (e: DragEvent, tabId: string): void => {
  dragSourceId.value = tabId
  e.dataTransfer?.setData('text/plain', tabId)
  e.dataTransfer!.effectAllowed = 'move'
}

const handleDragOver = (e: DragEvent): void => {
  e.preventDefault()
  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = 'move'
  }
}

const handleDrop = (e: DragEvent, targetId: string): void => {
  e.preventDefault()
  if (!dragSourceId.value || dragSourceId.value === targetId) {
    return
  }

  const currentIds = allTabs.value.map((t) => t.id)
  const sourceIndex = currentIds.indexOf(dragSourceId.value)
  const targetIndex = currentIds.indexOf(targetId)

  if (sourceIndex === -1 || targetIndex === -1) {
    return
  }

  const newOrder = [...currentIds]
  newOrder.splice(sourceIndex, 1)
  newOrder.splice(targetIndex, 0, dragSourceId.value)

  window.ipc.invoke(IPC_CHANNELS.TABS_REORDER_FROM_MENU, newOrder).then(() => {
    allTabs.value = newOrder.map((id) => allTabs.value.find((tab) => tab.id === id)).filter((tab): tab is Tab => tab !== undefined)
  })

  dragSourceId.value = null
}

const handleDragEnd = (): void => {
  dragSourceId.value = null
}

const handleCloseTab = (tabId: string): void => {
  window.ipc.invoke(IPC_CHANNELS.TABS_MENU_CLOSE_TAB, tabId)
}

window.initTabs = (activeId: string, tabs: Tab[]) => {
  currentActiveId = activeId
  currentTabs = tabs
  allTabs.value = tabs
}

window.ipc.on(IPC_CHANNELS.RENDERER_MONITOR_TABS_UPDATED, (data: { activeId: string; tabs: Tab[] }) => {
  window.logger.info('标签页更新:')
  currentActiveId = data.activeId
  currentTabs = data.tabs
  allTabs.value = data.tabs
})
</script>

<template>
  <n-config-provider :date-locale="dateZhCN" :locale="zhCN" :theme="null" :theme-overrides="commonThemeOverrides">
    <n-global-style />
    <n-message-provider>
      <n-flex class="app-container" vertical>
        <div class="search-box">
          <n-input
            v-model:value="searchKeyword"
            clearable
            placeholder="搜索标签页"
            round
            type="text"
            @clear="
              () => {
                allTabs = currentTabs
              }
            "
            @input="filterTabs"
          />
        </div>
        <div id="tabList" class="tab-list">
          <div
            v-for="tab in allTabs"
            :key="tab.id"
            :class="tab.id == currentActiveId ? 'active' : ''"
            draggable="true"
            @dragend="handleDragEnd"
            @dragover="handleDragOver"
            @dragstart="(e) => handleDragStart(e, tab.id)"
            @drop="(e) => handleDrop(e, tab.id)"
          >
            <n-space>
              <n-button text>
                <template #icon>
                  <n-image :src="tab.favicon" height="16" width="16" />
                </template>
                <n-ellipsis style="width: 190px; text-align: left">{{ tab.title }}</n-ellipsis>
              </n-button>
              <n-button circle class="drag-icon" text>
                <n-icon size="18">
                  <i-hugeicons-drag-drop-vertical />
                </n-icon>
              </n-button>
              <n-button circle class="close-icon" text @click.stop="handleCloseTab(tab.id)">
                <n-icon size="18">
                  <i-hugeicons-cancel-01 />
                </n-icon>
              </n-button>
            </n-space>
          </div>
        </div>
      </n-flex>
    </n-message-provider>
  </n-config-provider>
</template>

<style lang="scss" scoped>
:deep(.n-menu-item-content) {
  padding-left: 0 !important;
}

.app-container {
  height: 100vh;
  padding: 12px;
}
.search-box {
  padding-bottom: 8px;
  border-bottom: 1px solid #e0e0e0;
}

.drag-icon {
  padding-top: 6px;
  cursor: move;
  user-select: none;
}

.close-icon {
  padding-top: 6px;
  user-select: none;
}
</style>
