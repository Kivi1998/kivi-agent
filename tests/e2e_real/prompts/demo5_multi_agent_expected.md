# demo5_multi_agent 期望输出（agent: package-e2e-real-w82）

## Demo 5：综合多能力 Agent 真实 LLM 跑通验收标准

### 输入

- 任务描述：3 个子问题（年假政策 + 外部市场 + 区域数据 → 综合建议）
- 模型：Anthropic `claude-sonnet-4-6`（或 OpenAI 兼容模型）
- 真实 LLM + 真实 RAG / web_search / database / echarts_render

### 期望输出形态

1. **报告**：4 个 section（内部政策 / 外部市场 / 数据库聚合 / 综合结论）
2. **ECharts metadata**：含 `option` 字典（series / xAxis / yAxis）
3. **RAG sources**：>= 1 条（带 `id`）
4. **web_results**：>= 1 条（带 `url`）
5. **db_rows**：>= 1 条

### 接受阈值

- `output_quality_score >= 4`（人工：4=报告 + 图表完整，5=综合结论有洞见）
- `success == True`
- `len(report_sections) == 4`（演示版固定 4 个 section）
- `chart_series_count >= 1`
- `len(rag_sources) >= 1` & `len(web_results) >= 1`

### 真实 LLM 风险点

- 综合 synthesizer 真实模式下 LLM 可能耗 token 较多 → 注意 cost_usd
- 真实 web_search 偶发超时 → 写 `error` 字段，partial success 仍可接受
- ECharts option 真实 LLM 可能生成不规范 → 仅校验 series >= 1
