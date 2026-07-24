# eval_routing 5 case 期望路由决策（agent: package-e2e-real-w82）

## 真实 LLM Eval 路由 5 case 期望

按 `docs/eval-demos/basic-routing-10cases.jsonl` 选前 5 个 case，期望路由如下：

| case_id | goal | expected_route | expected_tools |
|---------|------|----------------|----------------|
| case-01 | 什么是 KamaClaude 的核心架构？ | `rag` | `rag_query` |
| case-02 | 2026 年最新 GPT 模型叫什么？ | `web_search` | `web_search` |
| case-03 | 查一下 users 表里 id=1 的用户名 | `database` | `query_database` |
| case-04 | 你好，你叫什么？ | `general` | (空) |
| case-05 | 用柱状图对比 Q1 Q2 Q3 营收数据 | `synthesizer` | `query_database`, `echarts_render` |

### 接受阈值

- `output_quality_score >= 3`（人工：3=路由正确，4=工具选择正确，5=综合输出可用）
- `success == True`
- `route_decision.intent == expected_route`（硬性）
- `tool_calls` 含 `expected_tools`（硬性）

### 真实 LLM 风险点

- 真实 LLM 可能误判"用户你好"为 rag → 需 general 兜底逻辑生效
- LLM 偶发不确定（低 confidence） → `output_quality_score` 降
- multi-tool case（case-05）真实 LLM 可能漏调 echarts_render → 工具选择不完整
