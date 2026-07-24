# aigroup Wave 8.2：真实 LLM 端到端（Anthropic + OpenAI 双 provider）

> **基线**：`main @ 4fb25a6`（aigroup Wave 7 收官，1425 passed / 240 files / 端到端演示）
> **日期**：2026-07-23
> **承接关系**：Wave 7 已完成 5 演示用例 + 3 模式 Docker + 12 case 基线（全部 FakeLlmProvider）。Wave 8.2 把"真实 LLM 跑通"补上。
> **用户决定（2026-07-23）**：
>   1. 项目定位 = **个人项目 / 简历作品**
>   2. Wave 8 偏好 = **真实 LLM 端到端**（最有意思、能写到简历）
>   3. **支持 Anthropic + OpenAI 两种 key 接入**（用户自己有 key，**不主动跑真 LLM**，由用户 export key 后手动跑）

---

## 一、目标

把"组件齐全 + FakeLlmProvider 单测全过"升级为"真实 LLM 端到端能力"：

```
现有（Wave 1 + 6.1 + 7）
  AnthropicProvider（Wave 1 简单实现）
  OpenAICompatProvider（Wave 1 简单实现）
  所有 demos / eval / dashboard 用 FakeLlmProvider
新增（Wave 8.2）
  AnthropicProvider 增强（重试 / 超时 / Token 统计 / 流式）
  OpenAICompatProvider 增强（DeepSeek 兼容 / 重试 / 超时 / Token / 流式 / Embedding）
  真实 LLM E2E 框架（env guard：默认跳过）
  .env.example + RUNBOOK + README：怎么 export key 跑真 LLM
  报告模板：用户跑完后填，简历可直接引用
```

**核心交付**：
- 2 个 LLM provider 增强（Anthropic + OpenAI 兼容）
- 真实 LLM E2E 测试套件（5 demo + 5 eval case，env guard `KIVI_RUN_E2E=1`）
- 报告模板（token 成本 / 延迟 / 输出质量）
- 完整指南（怎么 export key + 跑真 LLM + 看报告）
- .env.example 加 `KIVI_ANTHROPIC_*` / `KIVI_OPENAI_*` env vars

**注意**：Wave 8.2 不主动跑真 LLM（避免扣 token）。用户 export key 后自己跑。

---

## 二、范围

### 2.1 必做（Wave 8.2 范围）

| 序号 | 任务 | 估时 | 交付 |
|---|---|---|---|
| L1 | AnthropicProvider 增强 | 1-2 天 | `src/kivi_agent/core/llm/provider.py` + tests |
| L2 | OpenAICompatProvider 增强 | 1-2 天 | `src/kivi_agent/core/llm/openai_compat_provider.py` + tests |
| L3 | 真实 LLM E2E 框架 | 2-3 天 | `tests/e2e_real/` + 报告模板 |
| L4 | 文档 + .env.example + RUNBOOK | 1-2 天 | `docs/e2e-real/` + README + RUNBOOK 更新 |
| 主控 | 集成 + 全量验证 + 收口 | 1 天 | 集成 commit + 收口记录 |

**总估时**：6-10 天，4 WT 并行 + 集成

### 2.2 现有 provider 状态

整合方案 5.2.3（部分）已完成。Wave 1 已实现：
- `AnthropicProvider`（`src/kivi_agent/core/llm/provider.py`）：基本 async 调用 + token 跟踪
- `OpenAICompatProvider`（`src/kivi_agent/core/llm/openai_compat_provider.py`）：基本 async 调用 + DeepSeek 兼容

需要补：
- 重试机制（429 / 500 / 503 exponential backoff）
- 超时（30s 默认，可配置）
- Token 统计（input / output / total）
- 流式响应（sse / chunk）
- 错误归一化（统一 exception 类型）
- config 暴露（model / temperature / max_tokens / timeout / max_retries）

### 2.3 验收标准

| 验收 | 拆到哪个 WT 验证 |
|---|---|
| 用户 export key 后能跑真 LLM | L1 + L2 + L4（文档） |
| 5 demo 真实 LLM 跑通 | L3（env-guard 测试） |
| 报告输出 token 成本 + 延迟 | L3 + L4（报告模板） |
| 不破坏现有 FakeLlmProvider 单测 | L1 + L2（default 仍 fake） |

---

## 三、4 个 WT 详细设计

### WT-L1: AnthropicProvider 增强

**目标**：生产级 Anthropic Claude 客户端，重试 / 超时 / Token 统计 / 流式

**代码位置**：
- `src/kivi_agent/core/llm/provider.py`（增强现有）
  - `class AnthropicProvider`:
    - 构造函数接受 `model: str, *, base_url: str | None = None, api_key: str, timeout: float = 30.0, max_retries: int = 3, temperature: float = 0.7, max_tokens: int = 4096`
    - `async complete(messages, tools=None) -> CompletionResult`：核心调用
    - `async stream_complete(messages) -> AsyncIterator[StreamChunk]`：流式
    - 错误归一化：`LLMRateLimitError` / `LLMTimeoutError` / `LLMUnavailableError`
    - 重试：429 / 500 / 503 exponential backoff（1s / 2s / 4s）
    - Token 跟踪：`usage.input_tokens` / `usage.output_tokens` / `usage.total_tokens`
  - `class CompletionResult`: content / tool_calls / usage / stop_reason
- `src/kivi_agent/core/llm/errors.py`（新建）：4 种异常类
- `src/kivi_agent/core/llm/factory.py`（增强）：`create_provider()` 支持 4 种参数 + env var 读取

**env vars**（K1 + L4 一起加）：
- `KIVI_ANTHROPIC_API_KEY=sk-ant-...`
- `KIVI_ANTHROPIC_BASE_URL=https://api.anthropic.com`（或 DeepSeek 兼容端点）
- `KIVI_LLM_DEFAULT_MODEL=claude-sonnet-4-6`
- `KIVI_LLM_TIMEOUT=30`
- `KIVI_LLM_MAX_RETRIES=3`

**测试**：
- `tests/unit/test_anthropic_provider.py`（20+ tests）：mock client / 重试 / 超时 / token 统计 / 流式
- `tests/integration/test_anthropic_provider_e2e.py`（3+ tests，env guard `KIVI_RUN_E2E=1` + `KIVI_ANTHROPIC_API_KEY` set）：真 LLM 单 prompt

**commit 规划**：3-4 commit
1. `feat(llm): AnthropicProvider 增强（重试 / 超时 / Token 统计 / 流式）`
2. `feat(llm): LLM 错误类型（LLMRateLimitError / LLMTimeoutError / LLMUnavailableError）`
3. `test(llm): AnthropicProvider 20+ 单测 + 3 集成（env guard）`
4. `fix(llm): 集成期 mypy 收尾（如需）`

### WT-L2: OpenAICompatProvider 增强

**目标**：生产级 OpenAI 兼容客户端（DeepSeek / OpenAI / Azure OpenAI / 任何 OpenAI 兼容服务），重试 / 超时 / Token / 流式 / Embedding

**代码位置**：
- `src/kivi_agent/core/llm/openai_compat_provider.py`（增强现有）
  - `class OpenAICompatProvider`:
    - 构造函数接受 `model: str, *, base_url: str, api_key: str, timeout: float = 30.0, max_retries: int = 3, temperature: float = 0.7, max_tokens: int = 4096`
    - `async complete(messages, tools=None) -> CompletionResult`：OpenAI Chat Completions API
    - `async stream_complete(messages) -> AsyncIterator[StreamChunk]`：流式（SSE）
    - 错误归一化：复用 L1 错误类型
    - 重试 + 超时：复用 L1 retry 机制
- `src/kivi_agent/core/memory/embedding/openai_compat.py`（增强 Wave 6.1 已实现的）：
  - 加 timeout / retry / batch_size 参数
- `src/kivi_agent/core/llm/factory.py`：增加 `create_provider()` OpenAI 分支

**env vars**：
- `KIVI_OPENAI_API_KEY=sk-...`
- `KIVI_OPENAI_BASE_URL=https://api.openai.com/v1`（或 DeepSeek: `https://api.deepseek.com/v1`）
- `KIVI_EMBEDDING_MODEL=text-embedding-3-small`
- `KIVI_EMBEDDING_BATCH_SIZE=100`

**测试**：
- `tests/unit/test_openai_compat_provider.py`（20+ tests）：mock client / DeepSeek 兼容 / 重试 / 超时 / 流式
- `tests/integration/test_openai_compat_e2e.py`（3+ tests，env guard `KIVI_RUN_E2E=1` + `KIVI_OPENAI_API_KEY` set）

**commit 规划**：3-4 commit
1. `feat(llm): OpenAICompatProvider 增强（DeepSeek 兼容 / 重试 / 超时 / Token / 流式）`
2. `feat(embedding): OpenAICompat Embedding batch + retry + timeout`
3. `test(llm): OpenAI 兼容 20+ 单测 + 3 集成（env guard）`
4. `fix(llm): 集成期 mypy 收尾（如需）`

### WT-L3: 真实 LLM E2E 框架

**目标**：5 demo + 5 eval case 真实 LLM 跑通框架（env guard 默认跳过），输出 token 成本 / 延迟 / 输出质量报告

**代码位置**：
- `tests/e2e_real/__init__.py`
- `tests/e2e_real/conftest.py`：env guard + report helpers
- `tests/e2e_real/test_demo1_coding_e2e.py`：demo1 真 LLM
- `tests/e2e_real/test_demo2_rag_e2e.py`：demo2 真 LLM
- `tests/e2e_real/test_demo3_database_e2e.py`：demo3 真 LLM
- `tests/e2e_real/test_demo4_frontend_map_e2e.py`：demo4 真 LLM
- `tests/e2e_real/test_demo5_multi_agent_e2e.py`：demo5 真 LLM
- `tests/e2e_real/test_eval_routing_e2e.py`：5 eval case 真 LLM
- `tests/e2e_real/report.py`：`E2EReport` 类（JSON + Markdown 双格式）
- `tests/e2e_real/prompts/`：5 demo + 5 eval 期望输出 fixture
- `tests/e2e_real/fixtures/`：mock 答案 / 接受阈值

**env guard**：
- `KIVI_RUN_E2E=1`：启用所有 e2e_real 测试
- `KIVI_E2E_PROVIDER=anthropic|openai`：选 provider
- `KIVI_E2E_MAX_CASES=5`：限制跑几个 case（防 token 失控）
- `KIVI_E2E_REPORT_DIR=reports/e2e_real/`：报告输出目录

**报告字段**：
- `provider` / `model` / `started_at` / `ended_at` / `duration_seconds`
- `case_id` / `case_name` / `input_tokens` / `output_tokens` / `total_tokens`
- `cost_usd`（按 Wave 5.1 PricingTable 计算）
- `latency_seconds` / `success` / `error`
- `output_quality_score`（人工 0-5）
- `output_preview`（前 200 字符）

**测试**：
- `tests/unit/test_e2e_real_conftest.py`（10+ tests）：env guard / report 序列化
- `tests/unit/test_e2e_real_report.py`（8+ tests）：报告格式 / 字段校验）

**commit 规划**：3-4 commit
1. `feat(e2e): 真实 LLM E2E 框架（conftest + report + env guard）`
2. `test(e2e): 5 demo + 5 eval 真 LLM E2E case（env guard 默认跳过）`
3. `feat(e2e): 报告生成（JSON + Markdown）`
4. `fix(e2e): 集成期 mypy 收尾（如需）`

### WT-L4: 文档 + .env.example + RUNBOOK

**目标**：用户 export key 后能按文档跑真 LLM

**代码位置**：
- `.env.example`（增强 Wave 7 已写 13 段）：加 `KIVI_ANTHROPIC_*` / `KIVI_OPENAI_*` / `KIVI_LLM_*` / `KIVI_E2E_*` 段
- `docs/e2e-real/README.md`（新建）：完整真 LLM 端到端指南
  - 怎么 export key（Anthropic / OpenAI / DeepSeek 三种）
  - 怎么跑 5 demo 真 LLM
  - 怎么跑 5 eval case 真 LLM
  - 怎么读报告（JSON / Markdown）
  - 怎么控制成本（`KIVI_E2E_MAX_CASES`）
  - 故障排查（429 / 401 / 超时）
- `docs/e2e-real/RESULTS_TEMPLATE.md`：报告模板（用户跑完填）
- `RUNBOOK.md`（增强 Wave 7 已写）：新增"真实 LLM 端到端"章节
- `README.md`（增强 Wave 7 已写）：新增"Quick Start: Real LLM"章节
- `MIGRATION.md`（增强 Wave 7 已写）：更新 Wave 8.2 状态

**commit 规划**：3-4 commit
1. `chore(env): .env.example 加 KIVI_ANTHROPIC_* / KIVI_OPENAI_* / KIVI_LLM_* / KIVI_E2E_* 段`
2. `docs(e2e-real): 真 LLM 端到端指南 + 报告模板`
3. `docs: RUNBOOK + README + MIGRATION 增真实 LLM 章节`
4. `chore(test): pyproject.toml 加 e2e_real env guard 说明`

---

## 四、4 个 WT 集成顺序

```
L1 (anthropic) ─┐
L2 (openai)    ─┼─→ L3 (e2e 框架) → L4 (docs) → 主控集成
L3 (e2e 独立)   ─┤
L4 (docs 独立)   ─┘
```

**主控集成顺序**：
1. cherry-pick / rebase L1 → L2 → L3 → L4 到 `integration/aigroup-wave8-2`
2. 集成期修复
3. 全量验证：pytest / mypy / ruff / 前端 type-check/test/lint/build
4. env-guarded e2e_real 跑（如果有 key）：`KIVI_RUN_E2E=1 uv run pytest tests/e2e_real -q`
5. **不强制跑真 LLM**（避免扣 token）。如果用户 export key，主控会跑。
6. 收口记录
7. 合并 main + 推 GitHub + 清理 worktree

---

## 五、风险与边界

| 风险 | 缓解 |
|---|---|
| **真 LLM 跑 token 失控**（如 prompt 包含大量内容） | env guard `KIVI_E2E_MAX_CASES=5` 默认限制；用户 export key 才有 token 风险 |
| 集成时无法测试真 LLM（用户机器上没设 key） | 默认跳过 e2e_real；代码用 mock 验证；用户可手动跑 |
| L1 + L2 都改 factory.py 冲突 | 集成期手动合并两个 provider 工厂分支 |
| Wave 1 已实现的 provider 代码可能不够用 | L1 / L2 增强而不是重写，保留现有 interface 兼容 |
| 真 LLM 输出不稳定（同一 prompt 多次跑结果不同） | e2e_real 用宽松阈值（output quality 人工评 0-5，不卡具体字符串） |
| 真实 LLM 调用 Anthropic SDK 流式差异 | Wave 1 已用 anthropic 库；L1 不引入新依赖 |

---

## 六、收口判定

- [ ] 后端 pytest 全绿（基线 1425 + Wave 8.2 新增 ≥ 60 case）
- [ ] mypy 0 / ≥ 245 files（240 + 5-10 新文件）
- [ ] ruff 与 Wave 7 收口基线持平（45，**Wave 8.2 新增 0**）
- [ ] 前端 type-check / test / lint / build 全绿（基线 181 + Wave 8.2 新增 0）
- [ ] AnthropicProvider 增强（重试 / 超时 / Token / 流式）完成
- [ ] OpenAICompatProvider 增强（DeepSeek 兼容 / 重试 / 超时 / Token / 流式）完成
- [ ] env-guarded 真实 LLM E2E 框架（10+ case 默认跳过）
- [ ] .env.example 完整覆盖 Anthropic / OpenAI / LLM / E2E 段
- [ ] docs/e2e-real/ 完整（README + 报告模板 + RESULTS_TEMPLATE）
- [ ] RUNBOOK + README + MIGRATION 增真实 LLM 章节
- [ ] 4 个 Wave 8.2 worktree 合并后清理
- [ ] Ruff pre-existing 45 项基线（不阻塞 Wave 8.2 关闭）

---

## 七、Wave 8.2 → 后续

- **Wave 8.4**：Cross-Encoder Reranker 升级 + Redis Streams Exporter（替换 BM25）
- **Wave 8.1**：生产部署（k8s/Helm/TLS）— 仅在用户需要时
- **Wave 8.3**：多租户隔离 — 仅在用户需要时

Wave 8.2 完成后，kivi-agent 达到"简历作品级别"：真实 LLM 端到端能力完整、5 演示可重跑、报告可引用、文档齐全。用户可继续打磨个人项目或基于此推公司生产环境。

---

## 八、用户使用指南（Wave 8.2 收口后）

```bash
# 1. 用户 export key（任选其一）
export KIVI_ANTHROPIC_API_KEY=sk-ant-...
# 或
export KIVI_OPENAI_API_KEY=sk-...
export KIVI_OPENAI_BASE_URL=https://api.openai.com/v1  # 或 DeepSeek

# 2. 跑 5 demo 真 LLM
KIVI_RUN_E2E=1 KIVI_E2E_PROVIDER=anthropic uv run pytest tests/e2e_real -q

# 3. 看报告
cat reports/e2e_real/real_llm_run_*.json | jq
# 或
cat reports/e2e_real/real_llm_run_*.md

# 4. 简历引用
# 把真实 token 成本 + 延迟 + 输出质量截图填到 docs/e2e-real/RESULTS.md
```
