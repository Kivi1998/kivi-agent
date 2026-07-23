# Trace Dashboard 演示

> Wave 5.1 收口演示：5 路由 × 2 case = 10 条数据集，端到端跑通 `kivi-eval → EvalResultStore → /api/dashboard → Web Dashboard`。

## 数据集

`docs/eval-demos/basic-routing-10cases.jsonl`：

- 5 路由各 2 条：`rag` / `web_search` / `database` / `general` / `synthesizer`
- 覆盖单工具、双工具、三工具合成（见 `case-10` 三工具组合）
- 字段：`id` / `goal` / `expected_route` / `expected_tools` / `expected_sources` / `expected_answer` / `difficulty` / `tags` / `notes`
- 受 v1 契约约束：`expected_tools` 必须是 6 个业务 Tool 之一（`web_search` / `rag_query` / `query_database` / `echarts_render` / `memory_save` / `memory_recall`）

## 跑评测

```bash
# 1. 跑 10 条数据集（concurrent = 2）
uv run kivi-eval run \
  --dataset docs/eval-demos/basic-routing-10cases.jsonl \
  --output /tmp/wave5-demo-results.jsonl \
  --concurrency 2

# 2. 汇总
uv run kivi-eval summary --results /tmp/wave5-demo-results.jsonl
# Summary: 10/10 succeeded (100.0%); judge avg=1.00 (10 judged)
```

## 启动 Gateway + 看 Dashboard

```bash
# 1. 启动 Gateway（默认端口 8000）
uv run kivi-core
# 或：uv run uvicorn kivi_agent.gateway.main:create_app --factory --host 0.0.0.0 --port 8000

# 2. 启动 Web Chat Dashboard
cd apps/web-chat && npm run dev
# 浏览器打开 http://localhost:5173/dashboard
```

Dashboard 路由（前端 G4 提交 `b4e5059`）：

- `/dashboard` 总览：SummaryCard + RunsList + MetricsBar
- `/dashboard/runs/:runId` 单 run：MetricsBar + CaseTable + TraceTimeline
- `/dashboard/runs/:runId/cases/:caseId` 单 case：TraceTimeline 完整事件流

## 5 个 Gateway 端点

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/dashboard/summary` | 全局统计（run 数 / case 数 / 平均成功率） |
| GET | `/api/dashboard/runs` | run 列表（按 `started_at` 倒序，分页） |
| GET | `/api/dashboard/runs/{run_id}` | 单 run 全部 case |
| GET | `/api/dashboard/metrics/{run_id}` | 7 指标 JSON（task_success_rate / route_accuracy / tool_selection_accuracy / rag_citation_accuracy / avg_latency_seconds / total_tokens / total_cost_usd） |
| GET | `/api/dashboard/traces/{run_id}` | 事件 trace JSONL（6 个 v1 事件 type） |

## 7 个指标

- `task_success_rate` — case 成功率
- `route_accuracy` — 路由决策与 `expected_route` 对齐率
- `tool_selection_accuracy` — 调用工具与 `expected_tools` 对齐率
- `rag_citation_accuracy` — RAG 引用 ID 与 `expected_sources` 对齐率
- `avg_latency_seconds` — 单 case 平均延迟
- `total_tokens` — 总 token 用量（input + output）
- `total_cost_usd` — 按 `[pricing]` 段计算的总成本

## 已知限制

- G1 设计：每个 case 生成独立 `run_id`（不是一次评测共享一个 run_id），Dashboard 列表里会看到 10 个 run 各 1 case。Wave 5.2 / 6 会统一为“一次评测一个 run_id”。
- Dashboard.vue 内的 `computeSummaryFromCases` 是前端 fallback——当 metrics 端点不可用时退化用前端算 SummaryCard 3/7 指标。
- ECharts 全量引入导致 588KB chunk，build 阶段会报警告（计划未要求 code-split，本 WT 不处理）。
