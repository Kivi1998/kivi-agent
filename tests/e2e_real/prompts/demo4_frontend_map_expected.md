# demo4_frontend_map 期望输出（agent: package-e2e-real-w82）

## Demo 4：前端操作 Agent 真实 LLM 跑通验收标准

### 输入

- 任务描述：用户问"找最近的 3 个公园"
- GeoJSON URL：3 个公开 URL（fixture 内）
- 模型：Anthropic `claude-sonnet-4-6`（或 OpenAI 兼容模型）
- 真实 LLM + 真实 httpx fetch（KIVI_REAL_GEOJSON=1）

### 期望输出形态

1. **loaded_features_count**：每个 URL 至少 1 个 feature（真实 GeoJSON）
2. **bbox**：每个 URL 都有 bounding box（min_x / min_y / max_x / max_y）
3. **map.geojson_loaded 事件**：每个成功 URL 推 1 个事件到 EventBus
4. **layer_id**：含 parks-1 / parks-2 / parks-3

### 接受阈值

- `output_quality_score >= 3`（人工：3=至少 1 个 URL 成功，4=2 个成功，5=3 个成功）
- `success == True`（真实模式下要求至少 1 个 URL 成功）
- `ok_count >= 1`（真实模式宽松：至少 1 个 URL 200 OK）
- `loaded_features_count > 0`（每个成功 URL）
- `bbox is not None`（每个成功 URL）

### 真实 LLM 风险点

- 公开 GeoJSON URL 可能 404 / rate-limit → 真实模式 `ok_count >= 1` 即可
- LLM 可能不会去 web search GeoJSON URL → 直接 hardcode mock fixture
- network timeout → fixture 需 catch，写入 `error` 字段
- LLM 选错 URL（hallucinate）→ 0 个 ok，`output_quality_score = 1`
