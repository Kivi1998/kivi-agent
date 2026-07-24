# demo3_database 期望输出（agent: package-e2e-real-w82）

## Demo 3：数据库 Agent 真实 LLM 跑通验收标准

### 输入

- 任务描述：用户问"Q1 总营收是多少"
- 数据库：SQLite fixture（20 行 orders 表，覆盖 2026-Q1 / Q2 订单）
- 模型：Anthropic `claude-sonnet-4-6`（或 OpenAI 兼容模型）
- 真实 LLM（非演示版 Mock）

### 期望输出形态

1. **数字**：返回的 Q1 总营收 = 44500（= 8000+5000+3000+1500+9000+3500+2000+6000+4000+2500）
2. **表格**：rows 列表非空，至少 10 行 Q1 数据
3. **columns**：含 `month` / `region` / `amount`
4. **ECharts metadata**：含 `series` / `xAxis` / `yAxis` 字段

### 接受阈值

- `output_quality_score >= 3`（人工：3=算出 44500，4=含表格，5=含图表 metadata）
- `success == True`
- `q1_revenue == 44500`（硬性期望）
- `row_count >= 10`
- `chart_keys` 含 `series`

### 真实 LLM 风险点

- LLM 可能生成错 SQL → 数字可能非 44500 → `output_quality_score` 降
- SQLite 真实查询可能慢 → 注意 latency_seconds
- 真实 LLM 可能需要 retry（timeout）→ 记录在 `error` 字段
