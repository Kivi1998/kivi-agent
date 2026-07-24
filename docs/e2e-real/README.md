# 真实 LLM 端到端（Real LLM E2E）

> **Wave 8.2 交付**：用真实 LLM（Anthropic / OpenAI / DeepSeek）跑通 5 demo + 5 eval case 的端到端框架。
> **设计原则**：默认**全部跳过**（env guard `KIVI_RUN_E2E=1` 才跑），**不主动扣 token**。用户 export key 后手动跑。
> **本指南读者**：开发者 / 简历读者 / 任何想"亲手验证真实 LLM 能跑通"的人。

## 目录

1. [这是什么](#1-这是什么)
2. [Quick Start：3 种 key 接入](#2-quick-start3-种-key-接入)
3. [怎么跑 5 demo 真 LLM](#3-怎么跑-5-demo-真-llm)
4. [怎么跑 5 eval case 真 LLM](#4-怎么跑-5-eval-case-真-llm)
5. [怎么读报告](#5-怎么读报告)
6. [怎么控制成本](#6-怎么控制成本)
7. [故障排查](#7-故障排查)
8. [报告模板](#8-报告模板)
9. [架构与代码位置](#9-架构与代码位置)

---

## 1. 这是什么

### 1.1 与现有 Wave 1~7 测试的差异

| 维度 | Wave 1~7（`tests/e2e/` + `tests/e2e_real/`） | Wave 8.2 本框架（`tests/e2e_real/test_*_e2e.py`） |
|---|---|---|
| **LLM** | `FakeLlmProvider`（脚本化响应） | **真实 LLM**（Anthropic / OpenAI / DeepSeek） |
| **环境依赖** | 无（CI 友好） | **需要 API key**（`KIVI_ANTHROPIC_API_KEY` 或 `KIVI_OPENAI_API_KEY`） |
| **env guard** | 默认跑 | **默认跳过**（`KIVI_RUN_E2E=1` 才跑） |
| **报告字段** | pass / fail | pass / fail / token / cost / latency / quality score |
| **使用场景** | CI / 演示 | **简历引用** / 真实端到端验证 / 成本基准 |

### 1.2 测试覆盖

- **5 demo 真 LLM**（`tests/e2e_real/test_demo{1,2,3,4,5}_*_e2e.py`）
  - demo1 coding（修 bug + 跑 pytest）
  - demo2 RAG（问内部政策 + 引用溯源）
  - demo3 database（自然语言问数 + SQL 生成）
  - demo4 frontend map（加载 GeoJSON）
  - demo5 multi-agent（policy + external + chart + team）
- **5 eval routing case 真 LLM**（`tests/e2e_real/test_eval_routing_e2e.py`）
  - 5 条 `BusinessRouter` 关键词路由 case
  - 验证 `route_decision` 字段是否正确

### 1.3 输出报告

每个 case 生成 1 条记录：

```json
{
  "case_id": "demo1_coding",
  "case_name": "Coding Agent: 修 add 函数 bug",
  "provider": "anthropic",
  "model": "claude-sonnet-4-6",
  "started_at": "2026-07-23T14:30:21Z",
  "duration_seconds": 8.42,
  "input_tokens": 1234,
  "output_tokens": 567,
  "total_tokens": 1801,
  "cost_usd": 0.0123,
  "latency_seconds": 7.91,
  "success": true,
  "error": null,
  "output_quality_score": 4,
  "output_preview": "First 200 chars of LLM output..."
}
```

- **JSON 格式**：`reports/e2e_real/real_llm_run_<timestamp>.json`
- **Markdown 格式**：`reports/e2e_real/real_llm_run_<timestamp>.md`（简历可直接截图）

---

## 2. Quick Start：3 种 key 接入

### 方案 A：官方 Anthropic（最简单，推荐）

```bash
# 1. 复制 .env
cp .env.example .env

# 2. 取消注释 + 填 key
vim .env
# KIVI_ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxx
# KIVI_ANTHROPIC_BASE_URL=https://api.anthropic.com
```

### 方案 B：OpenAI 官方

```bash
cp .env.example .env
vim .env
# KIVI_OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxx
# KIVI_OPENAI_BASE_URL=https://api.openai.com/v1
# KIVI_OPENAI_MODEL=gpt-4o-mini
```

### 方案 C：DeepSeek（最便宜，约 Anthropic 1/30）

```bash
cp .env.example .env
vim .env

# DeepSeek 提供 Anthropic 兼容端点（方案 C-1）
# KIVI_ANTHROPIC_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
# KIVI_ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
# KIVI_LLM_DEFAULT_MODEL=deepseek-chat

# 或者用 DeepSeek 的 OpenAI 兼容端点（方案 C-2）
# KIVI_OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
# KIVI_OPENAI_BASE_URL=https://api.deepseek.com/v1
# KIVI_OPENAI_MODEL=deepseek-chat
```

> **价格参考**（2026-07，**仅参考**，以官方为准）：
>
> | Provider | Model | Input ($/M tok) | Output ($/M tok) |
> |---|---|---|---|
> | Anthropic | claude-sonnet-4-6 | 3.00 | 15.00 |
> | OpenAI | gpt-4o-mini | 0.15 | 0.60 |
> | DeepSeek | deepseek-chat | 0.14 | 0.28 |

---

## 3. 怎么跑 5 demo 真 LLM

```bash
# 1. 装依赖（如已装跳过）
uv sync

# 2. export 你的 key（**不要提交到 .env.example**）
export KIVI_ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxx
# 或
# export KIVI_OPENAI_API_KEY=sk-proj-xxxxxxxxxxxx

# 3. 启用真实 LLM 测试（默认全部跳过）
export KIVI_RUN_E2E=1
export KIVI_E2E_PROVIDER=anthropic   # 或 openai
export KIVI_E2E_MAX_CASES=5          # 限制 case 数量（防 token 失控）

# 4. 跑全部 5 demo + 5 eval case
uv run pytest tests/e2e_real -q

# 5. 跑单个 demo
uv run pytest tests/e2e_real/test_demo1_coding_e2e.py -v

# 6. 跑单个 case
uv run pytest tests/e2e_real/test_demo1_coding_e2e.py::test_coding_fix_bug -v
```

**预期输出**：

```
tests/e2e_real/test_demo1_coding_e2e.py ............              [ 20%]
tests/e2e_real/test_demo2_rag_e2e.py ............                 [ 40%]
tests/e2e_real/test_demo3_database_e2e.py ............            [ 60%]
tests/e2e_real/test_demo4_frontend_map_e2e.py ............        [ 80%]
tests/e2e_real/test_demo5_multi_agent_e2e.py ............         [ 90%]
tests/e2e_real/test_eval_routing_e2e.py .........                 [100%]
========================= 10 passed in 45.23s =========================
✓ E2E report: reports/e2e_real/real_llm_run_20260723_143021.json
✓ E2E report: reports/e2e_real/real_llm_run_20260723_143021.md
```

**未设 key 时的预期**：

```
tests/e2e_real/test_demo1_coding_e2e.py ssssssssssss              [ 20%]
...
========================= 10 skipped in 0.42s =========================
```

---

## 4. 怎么跑 5 eval case 真 LLM

5 eval case 是 `BusinessRouter` 路由决策验证（`tests/e2e_real/test_eval_routing_e2e.py`）：

```bash
# 与 demo 同一命令（pytest 跑 tests/e2e_real/ 下所有）
KIVI_RUN_E2E=1 KIVI_E2E_PROVIDER=anthropic uv run pytest tests/e2e_real -q
```

**5 条 eval case**（与 `docs/eval-demos/basic-routing-10cases.jsonl` 前 5 条对齐）：

| Case ID | 输入 | 期望路由 |
|---|---|---|
| `eval_route_01` | "我们公司年假政策是什么？" | `rag` |
| `eval_route_02` | "上海今天天气怎么样？" | `web_search` |
| `eval_route_03` | "上个季度销售额是多少？" | `database` |
| `eval_route_04` | "总结一下刚才的内容" | `synthesizer` |
| `eval_route_05` | "你好" | `general` |

**报告字段**：

```json
{
  "case_id": "eval_route_01",
  "case_name": "年假政策查询",
  "input": "我们公司年假政策是什么？",
  "expected_route": "rag",
  "actual_route": "rag",
  "route_match": true,
  "input_tokens": 245,
  "output_tokens": 18,
  "total_tokens": 263,
  "cost_usd": 0.0009,
  "latency_seconds": 1.42,
  "success": true
}
```

---

## 5. 怎么读报告

### 5.1 JSON 格式

```bash
# 看单次 run 的所有 case
cat reports/e2e_real/real_llm_run_*.json | jq '.cases[]'

# 汇总
cat reports/e2e_real/real_llm_run_*.json | jq '{
  provider: .provider,
  model: .model,
  total_cases: (.cases | length),
  success_rate: ([.cases[] | select(.success == true)] | length) / (.cases | length),
  total_tokens: ([.cases[].total_tokens] | add),
  total_cost_usd: ([.cases[].cost_usd] | add),
  avg_latency: ([.cases[].latency_seconds] | add / length)
}'

# 看失败的 case
cat reports/e2e_real/real_llm_run_*.json | jq '.cases[] | select(.success == false)'

# 找最贵的 case
cat reports/e2e_real/real_llm_run_*.json | jq '.cases | sort_by(-.cost_usd) | .[0]'
```

### 5.2 Markdown 格式（简历可直接引用）

```bash
# 直接看
cat reports/e2e_real/real_llm_run_*.md

# 复制到剪贴板（macOS）
cat reports/e2e_real/real_llm_run_*.md | pbcopy
```

**Markdown 示例**：

```markdown
# Real LLM E2E Run — 2026-07-23 14:30:21

## 汇总

| 指标 | 值 |
|---|---|
| Provider | anthropic |
| Model | claude-sonnet-4-6 |
| Total Cases | 10 |
| Success Rate | 100% (10/10) |
| Total Tokens | 12,345 |
| Total Cost (USD) | $0.0876 |
| Avg Latency | 3.42s |
| Total Duration | 45.23s |

## Per-Case

| Case ID | Input Tokens | Output Tokens | Total Tokens | Cost (USD) | Latency (s) | Success |
|---|---|---|---|---|---|---|
| demo1_coding | 1234 | 567 | 1801 | $0.0123 | 7.91 | ✅ |
| demo2_rag | 456 | 123 | 579 | $0.0045 | 2.13 | ✅ |
| ... |
```

<!-- screenshot: 报告 Markdown 渲染效果（用户跑完后截屏填入） -->

### 5.3 对比多次 run

```bash
# 列所有 run 的汇总
for f in reports/e2e_real/real_llm_run_*.json; do
  echo "=== $f ==="
  cat "$f" | jq '{
    run_id: .run_id,
    started_at: .started_at,
    success_rate: ([.cases[] | select(.success)] | length) / (.cases | length),
    total_cost: ([.cases[].cost_usd] | add)
  }'
done
```

---

## 6. 怎么控制成本

### 6.1 限制 case 数量

```bash
# 只跑前 2 个 case（最少 token 消耗验证框架）
export KIVI_E2E_MAX_CASES=2
KIVI_RUN_E2E=1 uv run pytest tests/e2e_real -q

# 跑 5 demo + 5 eval（10 个 case）
export KIVI_E2E_MAX_CASES=10
KIVI_RUN_E2E=1 uv run pytest tests/e2e_real -q
```

### 6.2 选便宜的 provider

```bash
# DeepSeek（最便宜，~ Anthropic 1/30）
export KIVI_ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
export KIVI_ANTHROPIC_API_KEY=sk-deepseek-xxx
export KIVI_LLM_DEFAULT_MODEL=deepseek-chat
export KIVI_RUN_E2E=1
export KIVI_E2E_PROVIDER=anthropic
uv run pytest tests/e2e_real -q
```

### 6.3 选便宜的 model

```bash
# OpenAI gpt-4o-mini（比 claude-sonnet-4-6 便宜 20x）
export KIVI_OPENAI_API_KEY=sk-proj-xxx
export KIVI_OPENAI_MODEL=gpt-4o-mini
export KIVI_RUN_E2E=1
export KIVI_E2E_PROVIDER=openai
uv run pytest tests/e2e_real -q
```

### 6.4 估算法

**5 demo + 5 eval case** 的典型 token 用量（**仅供参考**）：

| Provider | Model | Tokens / Case | 10 Cases | Cost (USD) |
|---|---|---|---|---|
| Anthropic | claude-sonnet-4-6 | ~1500 | ~15,000 | ~$0.10 |
| OpenAI | gpt-4o-mini | ~1500 | ~15,000 | ~$0.005 |
| DeepSeek | deepseek-chat | ~1500 | ~15,000 | ~$0.002 |

> **注意**：实际用量因 prompt 大小 + 工具调用次数 + 输出长度而异。**建议先用 1 个 case 试水**：`KIVI_E2E_MAX_CASES=1`。

---

## 7. 故障排查

### 7.1 401 Unauthorized（API key 错）

**症状**：

```
llm.call_failed: 401 Unauthorized
# 或
anthropic.AuthenticationError: Could not resolve authentication
```

**排查**：

```bash
# 1. 确认 key 已设
echo $KIVI_ANTHROPIC_API_KEY | head -c 12
# → sk-ant-api03 （前缀对了才是合法 key）

# 2. 用 curl 直接测
curl -fsS https://api.anthropic.com/v1/messages \
  -H "x-api-key: $KIVI_ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
```

**修复**：

- 重新从 [Anthropic Console](https://console.anthropic.com/) 复制 key
- 确认是 `sk-ant-...` 前缀（不是 `sk-` 旧版）
- 如使用 DeepSeek 走 Anthropic 兼容端点，key 是 `sk-deepseek-...` 格式

### 7.2 429 Too Many Requests（限流）

**症状**：

```
llm.call_failed: 429 Too Many Requests
# 重试 3 次后
llm.call_failed: 429 retry exhausted
```

**排查**：

```bash
# 看 retry 间隔（默认 1s / 2s / 4s exponential backoff）
KAMA_LOG_LEVEL=DEBUG uv run pytest tests/e2e_real -q -s
```

**修复**：

- **等几秒重跑**：429 通常是临时限流，30 秒后再试
- **降并发**：串行跑（不要 parallel）
- **换 provider**：DeepSeek 通常不限流
- **改 `KIVI_LLM_MAX_RETRIES=5`**：增加重试次数

### 7.3 Timeout（`httpx.ReadTimeout`）

**症状**：

```
llm.call_failed: timeout after 30s
# 或
asyncio.TimeoutError
```

**排查**：

```bash
# 1. 直连测延迟
time curl -fsS -m 60 https://api.anthropic.com/v1/messages \
  -H "x-api-key: $KIVI_ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
```

**修复**：

```bash
# 加大超时
export KIVI_LLM_TIMEOUT=120

# 加重试
export KIVI_LLM_MAX_RETRIES=3
```

### 7.4 5xx Server Error

**症状**：

```
llm.call_failed: 503 Service Unavailable
# 自动重试 3 次后成功 / 失败
```

**修复**：

- 这是 provider 端问题（Anthropic / OpenAI 自己挂了）
- L1/L2 已自动 exponential backoff 重试 3 次（1s / 2s / 4s）
- 如 3 次都失败，等几分钟后重跑

### 7.5 报告生成失败

**症状**：

```
PermissionError: [Errno 13] Permission denied: 'reports/e2e_real/...'
```

**修复**：

```bash
# 确认目录存在且可写
mkdir -p reports/e2e_real
chmod 755 reports/e2e_real

# 自定义报告目录
export KIVI_E2E_REPORT_DIR=/tmp/kivi-e2e/
```

### 7.6 全部 case 跳过

**症状**：

```
========================= 10 skipped in 0.42s =========================
```

**原因**：

- 未设 `KIVI_RUN_E2E=1`
- 或未设对应 provider 的 API key

**修复**：

```bash
# 两个都要设
export KIVI_RUN_E2E=1
export KIVI_ANTHROPIC_API_KEY=sk-ant-...   # 用 anthropic provider 时
# 或
export KIVI_OPENAI_API_KEY=sk-...           # 用 openai provider 时
```

---

## 8. 报告模板

详见 [RESULTS_TEMPLATE.md](./RESULTS_TEMPLATE.md)——用户跑完后填这个模板，**可直接引用到简历**。

**模板字段**：

- Provider / Model / Date
- Total Cases / Success Rate / Total Tokens / Total Cost (USD) / Avg Latency
- Per-Case Summary（5 demo + 5 eval 逐条记录）
- 5 demo 期望输出（每段 1 个 demo 的实际结果）
- 5 eval case 路由决策（每条 case 的 expected vs actual route）

---

## 9. 架构与代码位置

### 9.1 代码结构

```
tests/e2e_real/
├── __init__.py
├── conftest.py                    # env guard + fixtures
├── test_demo1_coding_e2e.py       # demo 1 真 LLM
├── test_demo2_rag_e2e.py          # demo 2 真 LLM
├── test_demo3_database_e2e.py     # demo 3 真 LLM
├── test_demo4_frontend_map_e2e.py # demo 4 真 LLM
├── test_demo5_multi_agent_e2e.py  # demo 5 真 LLM
├── test_eval_routing_e2e.py       # 5 eval routing case
├── report.py                      # E2EReport 类（JSON + Markdown）
├── prompts/                       # 5 demo + 5 eval 期望输出 fixture
│   ├── demo1_coding_expected.md
│   ├── demo2_rag_expected.md
│   ├── ...
│   └── eval_routing_expected.jsonl
└── fixtures/                      # mock 答案 / 接受阈值
```

### 9.2 Provider 增强

- **AnthropicProvider**（`src/kivi_agent/core/llm/provider.py`）— L1 增强
  - 重试（429 / 5xx exponential backoff）
  - 超时（30s 默认，可配置）
  - Token 统计（input / output / total）
  - 流式（`stream_complete` async generator）
  - 错误归一化（`LLMRateLimitError` / `LLMTimeoutError` / `LLMUnavailableError`）
- **OpenAICompatProvider**（`src/kivi_agent/core/llm/openai_compat_provider.py`）— L2 增强
  - 复用 AnthropicProvider 的重试 / 超时 / Token 框架
  - DeepSeek 兼容（`base_url` 可配）
  - OpenAI Embedding batch（`KIVI_EMBEDDING_BATCH_SIZE`）

### 9.3 env guard 实现

`tests/e2e_real/conftest.py` 顶层：

```python
import os
import pytest

# 默认跳过（KIVI_RUN_E2E=1 才跑）
if os.environ.get("KIVI_RUN_E2E") != "1":
    pytest.skip("Real LLM E2E tests skipped (set KIVI_RUN_E2E=1 to enable)",
                allow_module_level=True)
```

`tests/e2e_real/test_eval_routing_e2e.py` 顶层（provider 检查）：

```python
import os
import pytest

provider = os.environ.get("KIVI_E2E_PROVIDER", "anthropic")
if provider == "anthropic" and not os.environ.get("KIVI_ANTHROPIC_API_KEY"):
    pytest.skip("Anthropic API key not set", allow_module_level=True)
if provider == "openai" and not os.environ.get("KIVI_OPENAI_API_KEY"):
    pytest.skip("OpenAI API key not set", allow_module_level=True)
```

### 9.4 报告生成

`tests/e2e_real/report.py`：

```python
class E2EReport:
    """真实 LLM E2E 报告生成（JSON + Markdown 双格式）。"""
    
    def __init__(self, run_id: str, provider: str, model: str):
        self.run_id = run_id
        self.provider = provider
        self.model = model
        self.cases: list[dict] = []
        self.started_at: str = ""
        self.ended_at: str = ""
    
    def add_case(self, case: dict) -> None:
        """添加 1 个 case 结果。"""
        self.cases.append(case)
    
    def summary(self) -> dict:
        """汇总（success_rate / total_tokens / total_cost 等）。"""
        ...
    
    def to_json(self) -> str:
        """序列化为 JSON 字符串。"""
        ...
    
    def to_markdown(self) -> str:
        """渲染为 Markdown 表格。"""
        ...
```

---

## 10. 相关文档

- **[RESULTS_TEMPLATE.md](./RESULTS_TEMPLATE.md)**：用户跑完后填的报告模板（简历可引用）
- **[.env.example](../../.env.example)**：所有 env var 完整清单
- **[RUNBOOK.md §真实 LLM 端到端](../../RUNBOOK.md#7-真实-llm-端到端)**：运维视角的操作手册
- **[MIGRATION.md §Wave 8.2](../../MIGRATION.md#18-wave-82真实-llm-端到端-2026-07-23本波次)**：迁移清单
- **[plan §三 WT-L4](../superpowers/plans/2026-07-23-aigroup-wave8-2-real-llm-e2e.md#wt-l4-文档--envexample--runbook)**：WT-L4 设计
- **[plan §三 WT-L1](..//superpowers/plans/2026-07-23-aigroup-wave8-2-real-llm-e2e.md#wt-l1-anthropicprovider-增强)**：AnthropicProvider 增强
- **[plan §三 WT-L2](../superpowers/plans/2026-07-23-aigroup-wave8-2-real-llm-e2e.md#wt-l2-openaicompatprovider-增强)**：OpenAICompatProvider 增强
- **[plan §三 WT-L3](../superpowers/plans/2026-07-23-aigroup-wave8-2-real-llm-e2e.md#wt-l3-真实-llm-e2e-框架)**：E2E 框架
