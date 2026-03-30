<script lang="ts" setup>
import { dateZhCN, zhCN } from 'naive-ui'
import { commonThemeOverrides } from '@infound/desktop-base'
</script>

<template>
  <n-config-provider :date-locale="dateZhCN" :locale="zhCN" :theme="null" :theme-overrides="commonThemeOverrides">
    <n-global-style />
    <n-message-provider>
      <RouterView v-slot="{ Component }">
        <component :is="Component" />
      </RouterView>
    </n-message-provider>
  </n-config-provider>
</template>

<style lang="scss" scoped></style>
