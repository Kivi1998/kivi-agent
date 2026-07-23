<script setup lang="ts">
// 最小占位 App：WT-E2 集成期会被真正的 SessionList / ChatView 替换
// 本 WT 不实现 SessionList / ChatView（WT-E2 范围）
</script>

<template>
  <main class="app-shell">
    <header class="app-header">
      <h1>Kama Web Chat (Wave 3 / WT-E3 占位)</h1>
      <p>完整 UI 由 WT-E2 提供；本 WT 仅交付 3 个业务事件组件 + composable。</p>
    </header>
  </main>
</template>

<style scoped>
.app-shell {
  padding: 24px;
  max-width: 960px;
  margin: 0 auto;
}
.app-header h1 {
  font-size: 20px;
  margin-bottom: 8px;
}
.app-header p {
  color: var(--muted-color);
  font-size: 14px;
}
</style>
