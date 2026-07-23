# 贡献指南

> kivi-agent 欢迎所有形式的贡献：Bug 报告、Feature Request、文档改进、代码 PR。
> 本文档定义**代码风格、测试规范、PR 流程、Commit 规范、Sub-agent 任务模板**——按这些规则走能让集成期零冲突。

## 目录

1. [代码风格](#1-代码风格)
2. [测试规范](#2-测试规范)
3. [PR 流程（4-WT 并行 → 主控集成）](#3-pr-流程4-wt-并行--主控集成)
4. [Commit 规范](#4-commit-规范)
5. [Sub-agent 任务模板](#5-sub-agent-任务模板)
6. [开发环境设置](#6-开发环境设置)

---

## 1. 代码风格

### 1.1 工具链

- **Ruff**：lint + import 排序（`ruff check` + `ruff check --fix`）
- **Mypy**：严格类型检查（`mypy src`）
- **Python 版本**：3.12（由 `uv` 自动管理，参见 `.python-version`）
- **行宽**：100 字符（`pyproject.toml [tool.ruff]`）

### 1.2 类型注解

- **强制**：所有函数签名必须有完整类型注解（参数 + 返回）
- **Pydantic 模型**：用 `BaseModel` + 字段类型注解
- **Optional / Union**：用 `T | None` 形式（Python 3.10+ 新语法）
- **泛型**：`list[T]` / `dict[K, V]` / `tuple[T, ...]`（不用 `List` / `Dict` / `Tuple` from typing）
- **Literal**：枚举用 `Literal["a", "b"]`
- **Protocol**：duck typing 用 `typing.Protocol`

**示例**：

```python
from typing import Literal
from pydantic import BaseModel


class MemoryItem(BaseModel):
    id: str
    content: str
    type: Literal["user", "feedback", "project", "reference", "task"]
    importance: float  # 0.0-1.0


async def recall(query: str, top_k: int = 5) -> list[MemoryItem]:
    """检索相关记忆。"""
    ...
```

### 1.3 中文 docstring

- 模块级 docstring 用中文
- 函数 / 类 docstring 用中文（一句话职责 + Args / Returns / Raises 三段式）
- 复杂逻辑（多步算法、并发控制）加中文 # 注释
- **保持简练**：不要复述代码，只写"为什么"和"做什么"

**示例**：

```python
"""长期记忆后端协议（Wave 6.1 J1 实施）。

MemoryBackend 是 Local / Vector 两实现的抽象接口，
所有业务 Tool 通过此接口读写，零侵入切换。
"""

from __future__ import annotations

from typing import Protocol

from kivi_agent.core.memory.types import MemoryItem


class MemoryBackend(Protocol):
    """长期记忆后端协议。

    Args:
        item: 记忆条目。

    Returns:
        写入是否成功。

    Raises:
        MemoryBackendError: 后端不可用且未配置 fallback。
    """

    async def save(self, item: MemoryItem) -> bool:
        """写入记忆。失败抛 MemoryBackendError。"""
        ...


async def recall(
    backend: MemoryBackend,
    query: str,
    top_k: int = 5,
) -> list[MemoryItem]:
    """从后端检索 top_k 相关记忆。

    实现层负责向量检索 / BM25 rerank，调用方只关心结果。
    """
    ...
```

### 1.4 测试注释规范

测试文件用中文 docstring + 中文 # 注释，每个测试一段说明"测什么"：

```python
"""记忆后端协议测试。"""

import pytest
from kivi_agent.core.memory.types import MemoryItem


@pytest.mark.asyncio
async def test_local_backend_save_and_recall(tmp_path) -> None:
    """Local 后端：写入后立即可读，内容一致。"""
    backend = LocalMemoryBackend(root=tmp_path)
    item = MemoryItem(id="m1", content="hello", type="user", importance=0.5)

    assert await backend.save(item) is True
    results = await backend.recall("hello", top_k=5)
    assert len(results) == 1
    assert results[0].content == "hello"


@pytest.mark.asyncio
async def test_vector_backend_fallback_to_local_when_es_unavailable(monkeypatch) -> None:
    """Vector 后端：ES 不可用时自动降级到 Local（不抛异常）。"""
    # 模拟 ES 不可用
    monkeypatch.setenv("KIVI_ES_URL", "http://localhost:1")  # 故意连不上的端口

    backend = create_vector_backend_with_fallback()
    item = MemoryItem(id="m2", content="fallback test", type="user", importance=0.5)

    # 应自动降级到 Local，写入成功
    assert await backend.save(item) is True
    # 不应抛 ConnectionError
```

### 1.5 Import 顺序（Ruff 自动处理）

Ruff `I` 规则自动排序：

```python
# 1. __future__ imports（必须在最前）
from __future__ import annotations

# 2. 标准库
import asyncio
import json
from pathlib import Path

# 3. 第三方库
import httpx
from pydantic import BaseModel

# 4. 第一方（kivi_agent.*）
from kivi_agent.core.bus.events import Event
from kivi_agent.eval.result import EvalResult
```

### 1.6 命名

- **模块名**：`snake_case`（`business_router.py` / `vector_backend.py`）
- **类名**：`PascalCase`（`BusinessRouter` / `VectorMemoryBackend`）
- **函数 / 变量**：`snake_case`（`route_query` / `target_profiles`）
- **常量**：`UPPER_SNAKE`（`DEFAULT_POLICIES` / `MAX_STEPS`）
- **私有**：下划线前缀（`_internal_helper` / `_run_id`）
- **Type 变量**：`PascalCase`（`T` / `K` / `V` / `T_Model`）

### 1.7 错误处理

- **永远不** `except: pass`（必须指明异常类型 + 处理方式）
- **永远不** `except BaseException:`（除非要重新抛出）
- **业务异常**用自定义 Exception（`MemoryBackendError` / `RagKbError`）
- **fallback 不抛**：在 fallback 路径用 `logger.warning()` 而非 `raise`（保证主流程不挂）

**示例**：

```python
import logging

logger = logging.getLogger(__name__)


async def save(self, item: MemoryItem) -> bool:
    """写入记忆，失败降级到 Local。"""
    try:
        await self._es_client.index(index=self._index, id=item.id, document=item.model_dump())
    except (httpx.ConnectError, elasticsearch.ConnectionError) as e:
        # 真实服务不可用，降级到 Local（保证主流程不挂）
        logger.warning("ES unavailable, falling back to Local: %s", e)
        return await self._local_backend.save(item)
    return True
```

### 1.8 注释 / TODO 规范

- **TODO**：必须带 agent 标识（`# TODO(agent: package-x-vY): ...`）便于追踪
- **FIXME**：必须带 issue 链接或详细说明
- **XXX**：标记可疑代码，需要后续 review
- **NOTE**：说明设计决策（不需修复）

```python
# TODO(agent: package-vector-memory-v61): 接入 Periodic retry（每 60s 重试 ES）
# FIXME: #123 修复后去掉这个 fallback
# NOTE: 用 SHA-512 伪随机而非真实 Embedding，原因是演示版不要外部依赖
```

---

## 2. 测试规范

### 2.1 Pytest 模式

- **单测**（`tests/unit/`）：不需要 daemon / 外部服务，毫秒级
- **集成测试**（`tests/integration/`）：需要 daemon / Gateway / 真实进程
- **E2E 测试**（`tests/e2e/`）：需要真实外部服务（ES / Postgres / LLM）
- **契约测试**（`tests/contract/`）：验证 v1 协议契约不被破坏

### 2.2 命名

- **文件**：`test_*.py`（强制下划线）
- **函数**：`test_*`（强制下划线，防止 `tests_passed_rate` 被误收集）
- **类**：`Test*`（如要分组）
- **fixture**：`fixture_<name>` 或直接 `<name>`

### 2.3 异步测试

`asyncio_mode = "auto"`（已配），所有 `async def test_*` 自动被识别：

```python
import pytest


@pytest.mark.asyncio
async def test_async_function() -> None:
    """异步测试，无需显式 asyncio_mode。"""
    result = await some_async_function()
    assert result == expected
```

### 2.4 Fixture

- **范围**：`function`（默认）/ `class` / `module` / `session`
- **autouse**：仅在确实每个测试都要用时
- **共享**：放 `tests/conftest.py` 或 `tests/fixtures/`

```python
import pytest
from pathlib import Path


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """临时工作目录，含 src/ + tests/。"""
    workspace = tmp_path / "workspace"
    (workspace / "src").mkdir()
    (workspace / "tests").mkdir()
    return workspace


@pytest.fixture(scope="module")
def shared_es_client():
    """跨测试共享的 ES 客户端（性能优化）。"""
    client = create_es_client()
    yield client
    client.close()
```

### 2.5 Mock 模式

- **外部 API**：`monkeypatch` + `unittest.mock`
- **LLM Provider**：`FakeLlmProvider`（Wave 5.1 已有）
- **ES / DB**：`monkeypatch.setenv` 改 URL 到 `localhost:1`（不可达端口触发 fallback）

```python
def test_with_fake_llm() -> None:
    """用 FakeLlmProvider 注入 LLM 响应，避免真实 API 调用。"""
    fake = FakeLlmProvider(responses=[
        LlmResponse(text="hello", stop_reason="end_turn")
    ])
    runner = AgentRunner(provider=fake, ...)
    result = await runner.run("test")
    assert result.final_text == "hello"
```

### 2.6 Env Guard

不依赖外部服务的测试用 env guard 跳过：

```python
import os
import pytest


@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="需要真实 LLM API key 才能跑（默认跳过）"
)
def test_real_llm_e2e() -> None:
    """真实 LLM 端到端测试。"""
    ...
```

### 2.7 断言风格

- **不用 `assert True` / `assert False`**
- **复杂断言**：用 `pytest.approx`（浮点）/ 自定义 helper
- **错误信息**：assert 失败时打印有意义的值

```python
# 好
assert result.final_text == "hello"
assert result.usage.input_tokens == pytest.approx(135, abs=5)
assert len(result.tool_calls) == 1, f"expected 1 tool call, got {len(result.tool_calls)}"

# 不好
assert result  # 没说清测什么
```

### 2.8 覆盖率目标

- **新代码**：≥ 80% line coverage
- **核心模块**（`core/runner.py` / `core/loop.py` / `core/memory/`）：≥ 90%
- **业务 Tool**（`core/business/*`）：100%（Mock 实现 + 真实 Adapter 各 1 case）

---

## 3. PR 流程（4-WT 并行 → 主控集成）

kivi-agent 历经 Wave 1~6.1 全部采用 **4-WT 并行** 工作流。每个 Wave：

```
K1 (docker + 凭据清理) ─┐
K2 (5 demos)            ─┼─→ 主控集成（4 merge + 收口）
K3 (故障/性能/安全基线) ─┤
K4 (文档)               ─┘
```

### 3.1 4-WT 并行（开发者侧）

每个子包是一个独立 worktree（`kivi-agent-wt-{wt-name}`），按计划书的 TDD 任务红→绿→commit。

**执行步骤**：

1. **创建 worktree**（从 `main` 切出）
2. **读计划书**（`docs/superpowers/plans/2026-XX-XX-<plan>.md` §{WT-name}）
3. **逐任务 TDD**：先写测试（红）→ 写实现（绿）→ 重构（保绿）→ commit
4. **本地验证**：`uv run ruff check` + `uv run mypy src` + `uv run pytest tests/unit -v`
5. **不修改公共登记点**（`core/runner.py` / `core/permissions/policy.py` / `core/bus/*`），避免与其他 WT 冲突
6. **报告子包执行情况**：写 `{WT-name}-report.md`，含 commit 列表 + 已知调整

### 3.2 主控集成期

主控 agent 串行 merge 4 个 WT 到 `integration/aigroup-wave{N}`：

```bash
# 1. 切到集成分支
git checkout integration/aigroup-wave{N}

# 2. merge WT 1（按依赖顺序）
git merge --no-ff feature/wt-1 -m "merge: WT-1 ..."
# 冲突 → 手解（保留 WT 1 + 已有公共登记点）

# 3. merge WT 2-4 同样

# 4. 全量验证
uv run pytest tests/unit -v
uv run mypy src
uv run ruff check src tests
make verify-s0

# 5. 集成 commit（手解冲突 / 修集成发现）
git commit --allow-empty -m "fix: 集成期修复 ..."

# 6. 收口报告
# 写 docs/迁移记录/... 章节
git commit -m "docs: Wave N 收口报告"

# 7. 推 + 提 PR
git push origin integration/aigroup-wave{N}
# GitHub 提 PR → review → merge to main
```

### 3.3 PR Checklist

提交 PR 前**自检**：

- [ ] `uv run ruff check src tests` 0 新增错误
- [ ] `uv run mypy src` 0 error
- [ ] `uv run pytest tests/unit -v` 全过
- [ ] 新代码有测试（覆盖率 ≥ 80%）
- [ ] 中文 docstring + 中文 # 注释
- [ ] Commit 规范（`feat` / `fix` / `docs` / `chore` / `test`）
- [ ] 没引入真实 API key / 密码
- [ ] 没改 `WIRE_PROTOCOL.md`（自动生成）
- [ ] 没改 `docs/迁移记录/最小闭环验收记录.md`（历史归档）
- [ ] 如改了 `core/runner.py` / `core/permissions/policy.py` / `core/bus/*`，**必须**在 PR 描述说明理由

### 3.4 冲突处理

如果 4-WT merge 冲突：

| 冲突文件 | 处理方式 |
|---|---|
| `core/runner.py`（ToolRegistry 登记）| 保留所有 WT 的 register，按字母序排列 |
| `core/permissions/policy.py`（ToolPolicy）| 保留所有 WT 的 ToolPolicy，注释加 `# <tool>（agent: <wt>）` |
| `core/bus/events.py`（Event 联合）| 保留所有事件，Type 别名按字母序 |
| `core/bus/commands.py`（Command schema）| 同上 |
| 其他模块 | 看具体冲突，保留双方 |

---

## 4. Commit 规范

### 4.1 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

- **type**：`feat` / `fix` / `docs` / `chore` / `test` / `refactor` / `perf`
- **scope**：模块名（`memory` / `gateway` / `eval` / `business` / `tui` / `web-chat` / `agents` 等）
- **subject**：一句话描述，**中文，祈使句，< 50 字**
- **body**：详细说明（**中文**，解释"为什么" + 关键决策）
- **footer**：关联 issue / Breaking Change / agent 标识

### 4.2 Type 清单

| Type | 用途 | 示例 |
|---|---|---|
| `feat` | 新功能 | `feat(memory): VectorMemoryBackend + Embedding + BM25Reranker` |
| `fix` | Bug 修复 | `fix(memory): 集成期去重 local_backend.list_all` |
| `docs` | 文档 | `docs: README.md 重写（按 stage 8 验收）` |
| `chore` | 杂项 | `chore(ruff): 清理 Wave 1 新增 ruff 错误` |
| `test` | 测试 | `test(demos): 5 demo 跑通测试（mock LLM 注入）` |
| `refactor` | 重构 | `refactor: 提取 spawn_background_subagent 共享函数` |
| `perf` | 性能 | `perf(memory): Vector 检索缓存 query embedding` |

### 4.3 Scope 清单

| Scope | 对应目录 |
|---|---|
| `core` | `src/kivi_agent/core/` |
| `agents` | `src/kivi_agent/core/agents/` |
| `business` | `src/kivi_agent/core/business/` |
| `tools` | `src/kivi_agent/core/tools/` |
| `skills` | `src/kivi_agent/core/skills/` |
| `mcp` | `src/kivi_agent/core/mcp/` |
| `memory` | `src/kivi_agent/core/memory/` |
| `db` | `src/kivi_agent/core/db/` |
| `rag` | `src/kivi_agent/core/rag/` |
| `llm` | `src/kivi_agent/core/llm/` |
| `gateway` | `src/kivi_agent/gateway/` |
| `eval` | `src/kivi_agent/eval/` |
| `tui` | `src/kivi_agent/tui/` |
| `web-chat` | `apps/web-chat/` |
| `cli` | `src/kivi_agent/cli/` |
| `docs` | 文档 |
| `deps` | 依赖 |

### 4.4 示例

```bash
git commit -m "feat(memory): VectorMemoryBackend + Embedding + BM25Reranker

- VectorMemoryBackend（ES 8.x knn_vector dims=384）
- OpenAICompatEmbedding（与 LLM 共享 base URL）
- BM25Reranker（纯函数 + class 两种入口）
- 5 方法都包 try/except fallback 到 LocalMemoryBackend
- audit 独立索引 kivi-memory-audit（失败不重试不抛）

agent: package-vector-memory-v61"

git commit -m "fix(memory): 集成期去重 local_backend.list_all

J2 给 local_backend 加 list_all 时与 Wave 5.1 已有版本重复，
集成期删 J2 加的，保留 Wave 5.1 已有版本。

agent: integration-wave6-1"

git commit -m "docs: README.md 重写（按 stage 8 验收：可启动 / 5 demo / 不退化）

- 项目介绍 / 价值主张
- 环境要求（Python 3.12 / uv / Node 20 / Docker 可选）
- 快速开始（minimal / web / full 三模式 + curl 验证）
- 5 演示用例链接
- 文档索引 + 贡献链接 + 安全声明
- 5 分钟验证清单 + 状态与路线图

agent: package-docs-v7"
```

---

## 5. Sub-agent 任务模板

kivi-agent 历史波次大量用 sub-agent 并行（Wave 1~6.1 共 ~80 个 sub-agent）。以下为标准化任务模板。

### 5.1 任务书结构

每个 sub-agent 收到一份任务书，包含：

```markdown
# WT-{N}: {任务名}

> **基线**：`main @ <commit>`
> **执行者**：sub-agent 在 worktree `kivi-agent-wt-{name}` 上执行
> **目标**：{一句话目标}

## 一、范围

- {任务 1}
- {任务 2}
- ...

## 二、约束

- **不修改**：`core/runner.py` / `core/permissions/policy.py` / `core/bus/*`（公共登记点）
- **不引入**：新依赖（除非有充分理由且已在任务书列出）
- **测试覆盖率**：新代码 ≥ 80%
- **commit 数量**：{N} commit 内完成

## 三、验收标准

- [ ] 单元测试全过
- [ ] mypy 0 error
- [ ] ruff 0 新增
- [ ] 新增功能有测试覆盖
- [ ] 公共登记点未改（如必要改，在报告里说明理由）

## 四、commit 规划

1. `feat(...): ...`
2. `feat(...): ...`
3. `test(...): ...`
```

### 5.2 报告模板

sub-agent 完成后输出报告：

```markdown
# WT-{N} 报告

## commit 列表

| # | hash | subject |
|---|---|---|
| 1 | `abc1234` | feat(x): ... |
| 2 | `def5678` | feat(x): ... |
| 3 | `ghi9012` | test(x): ... |

## 测试

- `uv run pytest tests/unit -v` → X passed / 0 failed
- 新增 N 个测试文件 / M 个测试 case
- 覆盖率：{X}%

## 已知调整

| 调整 | 性质 | 原因 |
|---|---|---|
| {调整描述} | 必要 / 优化 / 妥协 | {为什么} |

## 集成注意

- 改了 `core/runner.py` 的 register 列表（增加 2 条），需要主控集成期合并
- 没改公共登记点
- 新增依赖：`httpx>=0.27`（已在任务书声明）
```

### 5.3 Sub-agent 调度（主控侧）

主控 agent 调度 sub-agent：

```python
# 用 Task 工具 / mavis team plan 调度
# 4 个 sub-agent 并行（独立 worktree）
sub_agents = [
    {"name": "wt-1", "worktree": "kivi-agent-wt-1", "task_book": "plans/...md"},
    {"name": "wt-2", "worktree": "kivi-agent-wt-2", "task_book": "plans/...md"},
    {"name": "wt-3", "worktree": "kivi-agent-wt-3", "task_book": "plans/...md"},
    {"name": "wt-4", "worktree": "kivi-agent-wt-4", "task_book": "plans/...md"},
]

# 并行启动，等待全部完成
results = await asyncio.gather(*[
    run_sub_agent(wt) for wt in sub_agents
])

# 主控集成
for result in results:
    merge_to_integration_branch(result.worktree, result.commit_list)
```

### 5.4 Sub-agent 编写建议

- **任务书越具体越好**：列出每个 commit 的预期 subject + 文件清单
- **公共登记点要明确指出**：sub-agent 不应该改什么要写清楚
- **测试要求写明**：覆盖率 / mock 模式 / env guard
- **报告模板给齐**：避免 sub-agent 输出格式混乱

---

## 6. 开发环境设置

### 6.1 一次性安装

```bash
# 1. 装 uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 装 Node.js 20+（前端开发需要）
brew install node   # macOS
# 或
# nvm install 20    # 跨平台

# 3. 装 Docker（full 模式需要）
brew install --cask docker  # macOS

# 4. clone + 同步
git clone <repo> && cd kivi-agent
uv sync
cp .env.example .env
```

### 6.2 IDE 配置

**VSCode**（推荐）：

`.vscode/settings.json`：

```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.linting.ruffEnabled": true,
  "python.linting.mypyEnabled": true,
  "[python]": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "charliermarsh.ruff"
  }
}
```

**PyCharm**：

- Settings → Project → Python Interpreter → Add → uv-managed
- Plugins → Ruff + Mypy
- Settings → Tools → File Watchers → + Ruff

### 6.3 日常开发循环

```bash
# 1. 拉最新
git pull origin main

# 2. 切分支
git checkout -b feat/your-feature

# 3. 写代码 + 测试
# （TDD：先写测试）

# 4. 验证
uv run ruff check src tests
uv run mypy src
uv run pytest tests/unit -v

# 5. 启 Core Daemon 调试（可选）
uv run kivi-core &

# 6. 提交
git add .
git commit -m "feat(scope): ..."
git push origin feat/your-feature

# 7. 提 PR
```

### 6.4 调试技巧

- **设 `KAMA_LOG_LEVEL=DEBUG`** 看详细日志
- **看 `~/.kivi/logs/core.log`** 找异常
- **看 `~/.kama/traces/daemon.jsonl`** 找事件流
- **Chrome DevTools** → WebSocket 面板看实时事件
- **`ipdb` / `pdb`** 打断点（不推荐在生产代码里）

---

## 7. 后续阅读

- **[modules.md](modules.md)**：按目录分章节的模块说明 + 关键文件清单
- **[../architecture/architecture.md](../architecture/architecture.md)**：整体架构 + 5 核心流程
- **[../architecture/data-flow.md](../architecture/data-flow.md)**：数据流 + 关键数据结构
- **[../../MIGRATION.md](../../MIGRATION.md)**：已迁移 / 未迁移 / 后续计划
- **[../../RUNBOOK.md](../../RUNBOOK.md)**：配置详解、启停、故障排查
