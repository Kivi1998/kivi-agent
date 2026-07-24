# kivi-agent 真实接入 E2E（agent: package-e2e-real-v4 + package-e2e-real-w82）

本目录同时承载 Wave 4 F4 与 Wave 8.2 L3 两类真实接入端到端测试。

## 1. Wave 4 v4（默认跑，无 token 风险）

`test_rag_real.py` + `test_db_real.py` + `test_fallback.py` 全部 11 个 case 默认
跑（无 env guard），覆盖：
- rag-kb mock in-process 启动 + 4 个真实模式场景
- SQLite/Postgres Adapter 真实模式
- 健康检查降级契约

详见原 v4 README 段落（保留向后兼容）。

## 2. Wave 8.2 w82 真实 LLM E2E（env guard 默认跳过）

5 demo + 5 eval case 用真实 Anthropic / OpenAI 兼容 LLM 跑通；记录 token /
cost / latency / success / 输出质量（人工 0-5）报告。

### 跑法（用户视角）

```bash
# 1. 准备 API key
export KIVI_ANTHROPIC_API_KEY=sk-ant-...
# 或
export KIVI_OPENAI_API_KEY=sk-...
export KIVI_OPENAI_BASE_URL=https://api.openai.com/v1

# 2. 跑真 LLM 端到端（默认 5 demo + 5 eval case）
KIVI_RUN_E2E=1 uv run pytest tests/e2e_real -q

# 3. 控制 provider / case 数 / 报告目录
KIVI_RUN_E2E=1 KIVI_E2E_PROVIDER=openai KIVI_E2E_MAX_CASES=3 \
  KIVI_E2E_REPORT_DIR=reports/e2e_real/ \
  uv run pytest tests/e2e_real -q
```

### env guard

| 变量 | 默认 | 作用 |
|------|------|------|
| `KIVI_RUN_E2E` | (unset) | 设 `"1"` 才跑 e2e_real；未设自动 skip |
| `KIVI_E2E_PROVIDER` | `anthropic` | 选 `anthropic` / `openai` 兼容 provider |
| `KIVI_E2E_MAX_CASES` | `5` | 限制 eval case 数（防 token 失控） |
| `KIVI_E2E_REPORT_DIR` | `reports/e2e_real/` | 报告输出目录 |

### 报告输出

跑完后 `KIVI_E2E_REPORT_DIR` 下会生成：
- `real_llm_e2e_run.json`（结构化）
- `real_llm_e2e_run.md`（人类可读 Markdown 表格）

报告字段：
- `provider` / `model` / `case_id` / `case_name` / `started_at` / `ended_at`
- `duration_seconds` / `input_tokens` / `output_tokens` / `total_tokens`
- `cost_usd`（按 PricingTable 计算）
- `success` / `error` / `output_quality_score`（人工评 0-5）
- `output_preview`（前 200 字符）

### 文件清单

| 路径 | 作用 |
|------|------|
| `__init__.py` | 目录说明 |
| `conftest.py` | env guard + llm_provider + max_cases + report_dir fixtures |
| `report.py` | E2ERunResult / E2EReport / make_run_result / compute_cost_usd |
| `_protocols.py` | LLMSimpleProvider Protocol（解耦 L1/L2） |
| `test_demo1_coding_e2e.py` | demo1 真实 LLM |
| `test_demo2_rag_e2e.py` | demo2 真实 LLM |
| `test_demo3_database_e2e.py` | demo3 真实 LLM |
| `test_demo4_frontend_map_e2e.py` | demo4 真实 LLM |
| `test_demo5_multi_agent_e2e.py` | demo5 真实 LLM |
| `test_eval_routing_e2e.py` | 5 eval case 真实 LLM |
| `prompts/demo1_coding_expected.md` ~ `eval_routing_expected.md` | 期望输出 |
| `fixtures/acceptance_thresholds.yaml` | 每个 demo 最低验收门槛 |

### K4 完整指南

WT-L4（docs worktree）会写完整版 `docs/e2e-real/README.md` + 报告模板
`docs/e2e-real/RESULTS_TEMPLATE.md`（含 token 成本 / 延迟 / 故障排查 / 简历
引用指南）。本 README 只做"怎么跑"短版。

### 故障排查

| 现象 | 原因 | 修复 |
|------|------|------|
| 所有 e2e_real case 全部 `SKIPPED` | `KIVI_RUN_E2E` 未设 | `export KIVI_RUN_E2E=1` |
| `RuntimeError: API key not set` | 缺 API key | `export KIVI_ANTHROPIC_API_KEY=...` |
| `cost_usd` 总是 0 | 模型不在 PricingTable | 检查 `report.py:DEFAULT_PRICING` |
| `output_quality_score` 总是 None | 人工评分未填 | 跑完后人工在 `.md` 报告里填 |

### 与 Wave 7 v4 边界

v4 与 w82 共享同一个 `tests/e2e_real/` 目录但互不依赖：
- v4 默认跑（无 env guard），11 个 case
- w82 默认 skip（需 `KIVI_RUN_E2E=1`），10+ case

`conftest.py` 已合并：v4 的 `rag_server` / `postgres_dsn` 与 w82 的
`env_guard` / `llm_provider` / `max_cases` / `report_dir` / `e2e_report` 并存。
