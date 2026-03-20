<script lang="ts" setup>
import { dateZhCN, zhCN } from 'naive-ui'
</script>

<template>
  <n-config-provider :date-locale="dateZhCN" :locale="zhCN" :theme="null" :theme-overrides="{ common: { fontWeightStrong: '600' } }">
    <n-global-style />
    <n-message-provider>
      <RouterView v-slot="{ Component }">
        <component :is="Component" />
      </RouterView>
    </n-message-provider>
  </n-config-provider>
</template>

<style lang="scss" scoped></style>
