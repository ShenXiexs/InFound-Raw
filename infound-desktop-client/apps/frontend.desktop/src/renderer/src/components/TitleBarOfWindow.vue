<script lang="ts" setup>
import { computed } from 'vue'
import { RendererState, rendererStore } from '@renderer/store/renderer-store'
import ButtonGroupOfTitleBar from '@renderer/components/ButtonGroupOfTitleBar.vue'
import { resolveResourceAssetUrl } from '@renderer/utils/asset-url'

const globalState: RendererState = rendererStore.currentState
const icon = computed(() => resolveResourceAssetUrl(globalState.appSetting.resourcesPath, 'icon.png'))
</script>

<template>
  <n-layout-header class="header">
    <div class="header-left">
      <n-avatar :src="icon" size="small" style="background-color: transparent" />
      <span class="header-title">寻达</span>
    </div>
    <div class="header-right">
      <button-group-of-title-bar />
    </div>
  </n-layout-header>
</template>

<style lang="scss" scoped>
@use '@renderer/assets/styles/title-bar.scss' as *;
</style>
