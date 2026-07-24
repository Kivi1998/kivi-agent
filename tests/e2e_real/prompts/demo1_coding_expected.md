# demo1_coding 期望输出（agent: package-e2e-real-w82）

## Demo 1：编程 Agent 真实 LLM 跑通验收标准

### 输入

- 任务描述：修复 `mymod.add(a, b)` 使其返回 `a + b`（fixture 含 `a - b` bug）
- 模型：Anthropic `claude-sonnet-4-6`（或 OpenAI 兼容模型）
- 真实 LLM（非 FakeLlmProvider）

### 期望输出形态

1. **最终代码形态**：LLM 返回 1 个完整 Python 文件 / patch，含正确 `return a + b`
2. **测试通过**：`test_add_basic` + `test_add_zero` 全部 pass
3. **指标**（与 Wave 7 demo1 对齐）：
   - `task_completion_rate.rate == 1.0`
   - `iteration_count` >= 1（至少跑 1 轮）
   - `self_recovery_rate.rate >= 0`（真实 LLM 可能无需 recovery）

### 接受阈值

- `output_quality_score >= 4`（人工：4=基本对，5=完美修复）
- `success == True`
- `input_tokens + output_tokens > 0`（确实调了 LLM）

### 真实 LLM 风险点

- LLM 可能给过于详细的解释 → 用较长 `output_tokens` 换 0/1 修复率
- 真实 LLM 可能直接 overwrite 整个文件 → 注意 patch 边界
- 真实 LLM 偶发 401 / 429 → fixture 需 catch 并写入 `error` 字段，不算 hard fail
