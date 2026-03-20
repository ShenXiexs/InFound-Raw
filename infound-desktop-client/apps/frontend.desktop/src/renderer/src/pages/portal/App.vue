<script lang="ts" setup>
import { dateZhCN, zhCN } from 'naive-ui'
import TitleBarOfWindow from '@renderer/components/TitleBarOfWindow.vue'
</script>

<template>
  <n-config-provider :date-locale="dateZhCN" :locale="zhCN" :theme="null" :theme-overrides="{ common: { fontWeightStrong: '600' } }">
    <n-global-style />
    <n-message-provider>
      <n-layout>
        <title-bar-of-window />
        <n-layout-content>
          <RouterView v-slot="{ Component }">
            <component :is="Component" />
          </RouterView>
        </n-layout-content>
      </n-layout>
    </n-message-provider>
  </n-config-provider>
</template>
