# demo2_rag 期望输出（agent: package-e2e-real-w82）

## Demo 2：知识库 Agent 真实 LLM 跑通验收标准

### 输入

- 任务描述：用户问"年假政策是什么"
- 知识库：`kb-policies`（含 3 篇政策文档）
- 模型：Anthropic `claude-sonnet-4-6`（或 OpenAI 兼容模型）
- 真实 LLM（非演示版 Mock）

### 期望输出形态

1. **answer**：含自然语言回答（>= 50 字符）
2. **source_id**：返回的 sources 列表含 `id`（非空字符串）
3. **ref_json**：answer 文本含 `<ref_json>...</ref_json>` 块（与 v1 §5.2.1 事件契约对齐）
4. **source_count >= 1**

### 接受阈值

- `output_quality_score >= 3`（人工：3=含基本政策要点，4=含数字 / 完整句子，5=完美）
- `success == True`
- `has_source_id == True`
- `has_ref_json == True`

### 真实 LLM 风险点

- 真实 RAG 后端可能超时 → 写入 `error` 字段，标记 `success=False`
- 真实 LLM 可能幻觉不在 source 中的内容 → `output_quality_score` 应 <= 3
- source 数量可能波动（真实检索） → 用宽松阈值 `source_count >= 1`
