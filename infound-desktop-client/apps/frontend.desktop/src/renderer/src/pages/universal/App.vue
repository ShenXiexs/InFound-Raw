<script lang="ts" setup>
import { dateZhCN, zhCN } from 'naive-ui'
</script>

<template>
  <n-config-provider
    :date-locale="dateZhCN"
    :locale="zhCN"
    :theme="null"
    :theme-overrides="{
      common: {
        fontWeightStrong: '600',
        primaryColor: '#8142f6',
        primaryColorHover: '#935cf7',
        primaryColorPressed: '#6f31e4',
        primaryColorSuppl: '#8142f6'
      }
    }"
  >
    <n-global-style />
    <n-message-provider>
      <RouterView v-slot="{ Component }">
        <component :is="Component" />
      </RouterView>
    </n-message-provider>
  </n-config-provider>
</template>

<style lang="scss" scoped></style>
