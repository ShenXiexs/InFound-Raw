<script lang="ts" setup></script>

<template>
  <n-flex align="center" justify="center" style="height: 100vh">
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
</template>
