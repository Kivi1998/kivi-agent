<script setup lang="ts">
import type { RouteDecision } from '../types/api'

/**
 * RoutePanel — 路由决策展示组件。
 *
 * 对应 TUI `src/kivi_agent/tui/route_panel.py`：cyan 卡片 + 意图 + 置信度
 * + target_profiles 链路 + matched keywords + 多意图警告。
 *
 * Props:
 *   decision - BusinessRouter.route(query) 的输出（由 route.decided 事件透传）
 */
defineProps<{
  decision: RouteDecision
}>()

// 置信度保留 2 位小数，与 TUI RoutePanel._header_text 行为一致
function formatConfidence(value: number): string {
  return value.toFixed(2)
}
</script>

<template>
  <section
    class="route-panel"
    data-testid="route-panel"
    :data-intent="decision.intent"
    :data-multi-intent="decision.is_multi_intent"
  >
    <header class="route-header">
      <span
        class="route-icon"
        aria-hidden="true"
      >🧭</span>
      <span class="route-title">路由决策</span>
      <span class="route-intent">intent={{ decision.intent }}</span>
      <span class="route-confidence">confidence={{ formatConfidence(decision.confidence) }}</span>
    </header>

    <div
      class="route-profiles"
      data-testid="route-profiles"
    >
      <span class="profiles-label">profiles:</span>
      <span
        v-for="(profile, index) in decision.target_profiles"
        :key="profile"
        class="profile-chip"
        :data-testid="`profile-chip-${profile}`"
      >
        {{ profile }}
        <span
          v-if="index < decision.target_profiles.length - 1"
          class="profile-arrow"
          aria-hidden="true"
        >→</span>
      </span>
    </div>

    <div
      v-if="decision.is_multi_intent"
      class="route-multi-intent"
      data-testid="route-multi-intent"
    >
      ⚠ 多意图（按优先级排序，synthesizer 兜底汇总）
    </div>

    <footer
      class="route-meta"
      data-testid="route-meta"
    >
      <span class="meta-label">matched:</span>
      <span
        v-if="decision.matched_keywords.length > 0"
        class="meta-keywords"
      >
        {{ decision.matched_keywords.join(', ') }}
      </span>
      <span
        v-else
        class="meta-empty"
      >(无关键词匹配)</span>
    </footer>
  </section>
</template>

<style scoped>
.route-panel {
  border: 1px solid var(--route-panel-color);
  border-radius: var(--border-radius);
  padding: var(--panel-padding);
  background: #ecfeff;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.route-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--route-panel-color);
  font-weight: 600;
}

.route-icon {
  font-size: 18px;
}

.route-title {
  font-size: 15px;
}

.route-intent,
.route-confidence {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  font-weight: 500;
}

.route-profiles {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  color: #1f2937;
  font-size: 14px;
}

.profiles-label {
  color: var(--muted-color);
  margin-right: 4px;
}

.profile-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  background: #ffffff;
  border: 1px solid var(--route-panel-color);
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: var(--route-panel-color);
}

.profile-arrow {
  margin-left: 6px;
  color: var(--route-panel-color);
  font-weight: 600;
}

.route-multi-intent {
  color: #b45309;
  background: #fef3c7;
  border-left: 3px solid #f59e0b;
  padding: 4px 8px;
  font-size: 13px;
  border-radius: 2px;
}

.route-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  color: var(--muted-color);
  font-size: 13px;
}

.meta-label {
  font-weight: 500;
}

.meta-keywords {
  color: #1f2937;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.meta-empty {
  font-style: italic;
  color: var(--muted-color);
}
</style>
