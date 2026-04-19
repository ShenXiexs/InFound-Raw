<script setup lang="ts">
import { NButton, NIcon, NTooltip } from 'naive-ui'

defineProps<{
  label: string
  tipText: string
}>()

const tooltipThemeOverrides = {
  color: 'rgba(30, 30, 30, 0.92)',
  textColor: '#ffffff',
  padding: '10px 12px',
  borderRadius: '8px',
  boxShadow: '0 4px 14px rgba(0, 0, 0, 0.2)'
}
</script>

<template>
  <span class="field-label-row">
    <span class="field-label-text">{{ label }}</span>
    <NTooltip placement="top" to="body" :show-arrow="true" :delay="80" :theme-overrides="tooltipThemeOverrides">
      <template #trigger>
        <NButton quaternary circle size="tiny" class="filter-help-btn" :focusable="false" tabindex="-1">
          <template #icon>
            <NIcon :size="16" class="filter-help-icon">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10" />
                <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </NIcon>
          </template>
        </NButton>
      </template>
      <div class="filter-help-tooltip-inner">{{ tipText }}</div>
    </NTooltip>
  </span>
</template>

<style scoped>
.field-label-row {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.field-label-text {
  font-size: 13px;
  color: #3c4a5b;
}

.filter-help-btn {
  flex-shrink: 0;
  width: 22px !important;
  height: 22px !important;
  min-width: 22px !important;
}

.filter-help-icon {
  color: #7d8da1;
}

.filter-help-tooltip-inner {
  max-width: 280px;
  font-size: 13px;
  line-height: 1.55;
  text-align: left;
  white-space: normal;
  word-break: break-word;
}
</style>
