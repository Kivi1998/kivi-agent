# kamaAgent 包B：模型能力与工具执行增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一目前分散在 `AnthropicProvider`/`OpenAICompatProvider` 里的模型上下文窗口硬编码表和流式聚合逻辑；给工具执行加并发批次（只读工具可并发跑）；给工具集加动态搜索/按需暴露机制。

**Architecture:** 四项改动互相独立，各自在现有模块上做局部扩展：`core/llm/catalog.py` 统一上下文窗口查表逻辑；`core/llm/streaming.py` 抽出 `OpenAICompatProvider` 内部手写的流式累积逻辑；`core/tools/executor.py` 新增并发批次执行，接入 `core/loop.py` 唯一的工具调用循环；`core/tools/registry.py` 扩展 `deferred`/`search` 机制。

**Tech Stack:** Python 3.12、pydantic v2、pytest + pytest-asyncio、uv。

## Global Constraints

- 遵守仓库 `CLAUDE.md`：每个函数上方一行中文注释；每个测试函数上方两行中文注释（`# 功能：`/`# 设计：`）。
- 测试命令：`uv run pytest tests/unit/test_xxx.py -v`；全量回归：`uv run pytest tests/unit -v`。
- **并发批次判断依赖 `BaseTool.category`**（包 D 已引入的字段，取值 `"read"|"write"|"command"|"other"`）——只有 `category == "read"` 的工具允许进同一个并发 batch，其余分类一律各自单独成批（串行）。这是本包和包 D 之间已知的接口耦合点，字段本身已经存在，本包只是消费它，不需要再协调。
- **不做模型上下文窗口的运行时远程探测**（M05 原计划里的"远端探测"）——静态内建表 + 默认回退值已经能覆盖当前实际接入的模型（Claude/DeepSeek/Moonshot），加一层网络探测是当前用不上的复杂度，YAGNI。
- **动态工具搜索机制本身要交付，但不强制迁移现有工具为 deferred**——`ToolRegistry` 加完 `deferred`/`search`/`mark_discovered` 能力后，是否把 `team_*`/MCP 工具标记成 deferred 属于后续按需决定的事，本包只交付机制。

---

### Task B1: 模型上下文窗口统一目录

**Files:**
- Create: `src/kivi_agent/core/llm/catalog.py`
- Modify: `src/kivi_agent/core/llm/provider.py`
- Modify: `src/kivi_agent/core/llm/openai_compat_provider.py`
- Test: `tests/unit/test_llm_catalog.py`

**Interfaces:**
- Produces: `def context_window_for(model: str) -> int`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_llm_catalog.py
from __future__ import annotations

from kivi_agent.core.llm.catalog import context_window_for


# 功能：验证已知模型返回内建表里的精确窗口大小
# 设计：覆盖 Claude 和 DeepSeek 各一个已知型号，确认两个 provider 原来各自维护的表被正确合并
def test_known_models_return_exact_window() -> None:
    assert context_window_for("claude-sonnet-4-6") == 200_000
    assert context_window_for("deepseek-v4-pro") == 128_000


# 功能：验证未知模型名返回默认回退值而不是报错
# 设计：新模型上线但表还没更新时，不应该让整个对话崩掉，覆盖这个降级路径
def test_unknown_model_returns_default_fallback() -> None:
    assert context_window_for("some-brand-new-model-2027") == 128_000
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_llm_catalog.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/llm/catalog.py
from __future__ import annotations

_DEFAULT_CONTEXT_WINDOW = 128_000

# 合并原先分散在 AnthropicProvider 和 OpenAICompatProvider 里的模型窗口表
_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "claude-opus-4-7": 200_000,
    "deepseek-v4-pro": 128_000,
    "deepseek-v4-flash": 128_000,
    "kimi-k2.6": 128_000,
}


# 返回指定模型的上下文窗口 token 数；未知模型返回默认回退值
def context_window_for(model: str) -> int:
    return _CONTEXT_WINDOWS.get(model, _DEFAULT_CONTEXT_WINDOW)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_llm_catalog.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 接入两个 Provider**

`core/llm/provider.py`：删除 `_MODEL_CONTEXT_WINDOWS` 字典和 `_context_window()` 函数，改为：

```python
from kivi_agent.core.llm.catalog import context_window_for
# ...
# 原 `_context_window(self._model)` 调用处改为：
context_pct = usage.input_tokens / context_window_for(self._model)
```

`core/llm/openai_compat_provider.py`：删除 `_DEFAULT_CONTEXT_WINDOW = 128_000` 常量，改为：

```python
from kivi_agent.core.llm.catalog import context_window_for
# ...
context_pct = input_tokens / context_window_for(self._model)
```

- [ ] **Step 6: 回归两个 Provider 的既有测试**

Run: `uv run pytest tests/unit/test_llm_provider.py tests/unit/test_openai_compat_provider.py -v`
Expected: 全部通过（确认替换没有改变行为，只是把硬编码表挪了位置）

- [ ] **Step 7: 提交**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-agent"
git add src/kivi_agent/core/llm/catalog.py src/kivi_agent/core/llm/provider.py \
        src/kivi_agent/core/llm/openai_compat_provider.py tests/unit/test_llm_catalog.py
git commit -m "feat: 统一模型上下文窗口目录，合并两个 Provider 各自维护的硬编码表"
```

---

### Task B2: 流式响应收集器

**Files:**
- Create: `src/kivi_agent/core/llm/streaming.py`
- Modify: `src/kivi_agent/core/llm/openai_compat_provider.py`
- Test: `tests/unit/test_streaming_collector.py`

**Interfaces:**
- Produces: `class StreamAccumulator`，`add_content_delta(text: str) -> None`、`add_tool_call_delta(index: int, id: str, name: str, arguments: str) -> None`、`finalize() -> tuple[str, list[ToolCallBlock]]`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_streaming_collector.py
from __future__ import annotations

from kivi_agent.core.llm.streaming import StreamAccumulator


# 功能：验证多个文本增量按顺序拼接成完整文本
# 设计：模拟流式返回的三个文本片段，断言 finalize 后拼接结果正确
def test_accumulator_joins_text_deltas() -> None:
    acc = StreamAccumulator()
    acc.add_content_delta("hel")
    acc.add_content_delta("lo")
    text, tool_calls = acc.finalize()
    assert text == "hello"
    assert tool_calls == []


# 功能：验证同一 index 的多个工具调用增量（id/name 各到一次、arguments 分片到达）能正确聚合成一个 ToolCallBlock
# 设计：这是 OpenAI 流式协议的真实行为——function.arguments 是逐字符/逐片段流式送达的 JSON 字符串，
#      必须按 index 累加而不是覆盖，覆盖这个核心聚合逻辑
def test_accumulator_aggregates_tool_call_by_index() -> None:
    acc = StreamAccumulator()
    acc.add_tool_call_delta(0, "call_1", "bash", '{"comm')
    acc.add_tool_call_delta(0, "", "", 'and": "ls"}')
    text, tool_calls = acc.finalize()
    assert len(tool_calls) == 1
    assert tool_calls[0].id == "call_1"
    assert tool_calls[0].name == "bash"
    assert tool_calls[0].input == {"command": "ls"}


# 功能：验证多个不同 index 的工具调用各自独立聚合，不会串到一起
# 设计：一次响应里模型并行发起两个工具调用是常见场景，覆盖多 tool_call 场景
def test_accumulator_handles_multiple_tool_calls() -> None:
    acc = StreamAccumulator()
    acc.add_tool_call_delta(0, "call_1", "read_file", '{"path": "a.py"}')
    acc.add_tool_call_delta(1, "call_2", "read_file", '{"path": "b.py"}')
    _, tool_calls = acc.finalize()
    assert len(tool_calls) == 2
    assert {tc.id for tc in tool_calls} == {"call_1", "call_2"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_streaming_collector.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/llm/streaming.py
from __future__ import annotations

import json

from kivi_agent.core.llm.types import ToolCallBlock


class StreamAccumulator:
    # 初始化空的文本片段列表和按 index 分组的工具调用缓冲区
    def __init__(self) -> None:
        self._text_parts: list[str] = []
        self._tool_call_buffers: dict[int, dict[str, str]] = {}

    # 追加一段文本增量
    def add_content_delta(self, text: str) -> None:
        self._text_parts.append(text)

    # 按 index 累加一次工具调用增量；id/name 只在非空时覆盖，arguments 始终追加
    def add_tool_call_delta(self, index: int, id: str, name: str, arguments: str) -> None:
        buf = self._tool_call_buffers.setdefault(index, {"id": "", "name": "", "arguments": ""})
        if id:
            buf["id"] = id
        if name:
            buf["name"] = name
        if arguments:
            buf["arguments"] += arguments

    # 聚合所有增量，返回完整文本和已解析的 ToolCallBlock 列表
    def finalize(self) -> tuple[str, list[ToolCallBlock]]:
        text = "".join(self._text_parts)
        tool_calls = [
            ToolCallBlock(id=buf["id"], name=buf["name"], input=json.loads(buf["arguments"] or "{}"))
            for buf in self._tool_call_buffers.values()
        ]
        return text, tool_calls
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_streaming_collector.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 接入 OpenAICompatProvider**

在 `core/llm/openai_compat_provider.py::chat()` 里，把手写的 `text_parts: list[str] = []` / `tool_call_buffers: dict[int, dict[str, str]] = {}` 替换为：

```python
        from kivi_agent.core.llm.streaming import StreamAccumulator
        acc = StreamAccumulator()
        usage: Any = None

        async for chunk in stream:
            if getattr(chunk, "usage", None) is not None:
                usage = chunk.usage
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta is None:
                continue
            if delta.content:
                acc.add_content_delta(delta.content)
                await bus.publish(LlmTokenEvent(run_id=run_id, token=delta.content, ts=_now()))
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    acc.add_tool_call_delta(
                        tc.index, tc.id or "", tc.function.name or "", tc.function.arguments or ""
                    )

        text, tool_calls = acc.finalize()
```

后续 `tool_calls = [...]` 那段手写解析逻辑整段删除（已经被 `acc.finalize()` 取代），`text_parts` 相关引用全部替换成上面的 `text` 变量。

- [ ] **Step 6: 回归**

Run: `uv run pytest tests/unit/test_openai_compat_provider.py -v`
Expected: 全部通过（原有两个测试断言的行为不变，只是内部实现换了）

- [ ] **Step 7: 提交**

```bash
git add src/kivi_agent/core/llm/streaming.py src/kivi_agent/core/llm/openai_compat_provider.py \
        tests/unit/test_streaming_collector.py
git commit -m "feat: 抽出 StreamAccumulator，统一 OpenAI 兼容流式增量聚合逻辑"
```

---

### Task B3: 工具并发批次执行

**Files:**
- Create: `src/kivi_agent/core/tools/executor.py`
- Modify: `src/kivi_agent/core/loop.py`
- Test: `tests/unit/test_tool_executor.py`

**Interfaces:**
- Consumes: `BaseTool.category`（包 D）、`invoke_tool`（已有）
- Produces: `def partition_tool_calls(tool_calls: list[ToolCallBlock], registry: ToolRegistry) -> list[list[ToolCallBlock]]`、`async def execute_tool_batches(batches, registry, bus, run_id, *, permission_manager, session_id, hook_engine) -> list[ToolResult]`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_tool_executor.py
from __future__ import annotations

from kivi_agent.core.llm.types import ToolCallBlock
from kivi_agent.core.tools.executor import partition_tool_calls
from kivi_agent.core.tools.registry import ToolRegistry
from kivi_agent.core.tools.builtin.read_file import ReadFileTool
from kivi_agent.core.tools.builtin.write_file import WriteFileTool


# 功能：验证连续的只读工具调用被分进同一个 batch
# 设计：两个 read_file 调用相邻出现，断言 partition 结果是一个长度为 2 的 batch，而不是拆成两批
def test_consecutive_read_calls_share_one_batch() -> None:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    calls = [
        ToolCallBlock(id="1", name="read_file", input={"path": "a.py"}),
        ToolCallBlock(id="2", name="read_file", input={"path": "b.py"}),
    ]
    batches = partition_tool_calls(calls, registry)
    assert batches == [calls]


# 功能：验证只读工具和写工具混在一起时，写工具单独成批，不和只读工具并发
# 设计：read/write/read 三个调用，断言分成 [read] [write] [read] 三批而不是全部合并，
#      覆盖"遇到非只读工具就切新批次"这个核心分组规则
def test_write_call_breaks_batch() -> None:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    calls = [
        ToolCallBlock(id="1", name="read_file", input={"path": "a.py"}),
        ToolCallBlock(id="2", name="write_file", input={"path": "b.py", "content": "x"}),
        ToolCallBlock(id="3", name="read_file", input={"path": "c.py"}),
    ]
    batches = partition_tool_calls(calls, registry)
    assert len(batches) == 3
    assert [b[0].name for b in batches] == ["read_file", "write_file", "read_file"]


# 功能：验证未知工具名（registry 里查不到）被当作非只读处理，单独成批而不是崩溃
# 设计：工具名拼错或还没注册时，保守起见当成非并发安全，覆盖这个防御性分支
def test_unknown_tool_is_treated_as_non_concurrent() -> None:
    registry = ToolRegistry()
    calls = [ToolCallBlock(id="1", name="nonexistent_tool", input={})]
    batches = partition_tool_calls(calls, registry)
    assert batches == [calls]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_tool_executor.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 partition_tool_calls**

```python
# src/kivi_agent/core/tools/executor.py
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from kivi_agent.core.llm.types import ToolCallBlock
from kivi_agent.core.tools.invocation import invoke_tool
from kivi_agent.core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from kivi_agent.core.events.bus import EventBus
    from kivi_agent.core.hooks.engine import HookEngine
    from kivi_agent.core.permissions.manager import PermissionManager
    from kivi_agent.core.tools.base import ToolResult


# 按 category 把连续的只读（"read"）工具调用分进同一批次；遇到非只读或未知工具单独成批
def partition_tool_calls(
    tool_calls: list[ToolCallBlock], registry: ToolRegistry
) -> list[list[ToolCallBlock]]:
    batches: list[list[ToolCallBlock]] = []
    current_read_batch: list[ToolCallBlock] = []

    for tc in tool_calls:
        tool = registry.get(tc.name)
        is_read = tool is not None and tool.category == "read"
        if is_read:
            current_read_batch.append(tc)
        else:
            if current_read_batch:
                batches.append(current_read_batch)
                current_read_batch = []
            batches.append([tc])

    if current_read_batch:
        batches.append(current_read_batch)

    return batches
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_tool_executor.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 实现批次执行函数**

```python
# 追加到 core/tools/executor.py

# 依次执行每个批次：批内工具调用并发跑（asyncio.gather），批与批之间串行，保持工具调用整体顺序稳定
async def execute_tool_batches(
    batches: list[list[ToolCallBlock]],
    registry: ToolRegistry,
    bus: EventBus,
    run_id: str,
    *,
    permission_manager: PermissionManager | None = None,
    session_id: str = "",
    hook_engine: HookEngine | None = None,
) -> list[tuple[ToolCallBlock, ToolResult]]:
    results: list[tuple[ToolCallBlock, ToolResult]] = []
    for batch in batches:
        batch_results = await asyncio.gather(*[
            invoke_tool(
                registry, tc, bus, run_id,
                permission_manager=permission_manager,
                session_id=session_id,
                hook_engine=hook_engine,
            )
            for tc in batch
        ])
        results.extend(zip(batch, batch_results, strict=True))
    return results
```

- [ ] **Step 6: 写批次执行的测试**

```python
# tests/unit/test_tool_executor.py 追加
from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.tools.executor import execute_tool_batches


# 功能：验证 execute_tool_batches 对每个 tool_call 都产出对应的 ToolResult，且顺序与输入一致
# 设计：两个 read_file 调用（会被分进同一并发批次），断言返回结果列表长度和顺序正确，
#      覆盖"并发执行不会打乱结果和原始调用的对应关系"这个关键正确性
async def test_execute_tool_batches_preserves_call_result_pairing(tmp_path) -> None:
    (tmp_path / "a.py").write_text("A")
    (tmp_path / "b.py").write_text("B")
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    calls = [
        ToolCallBlock(id="1", name="read_file", input={"path": str(tmp_path / "a.py")}),
        ToolCallBlock(id="2", name="read_file", input={"path": str(tmp_path / "b.py")}),
    ]
    batches = partition_tool_calls(calls, registry)
    pairs = await execute_tool_batches(batches, registry, EventBus(), run_id="r1")
    assert [tc.id for tc, _ in pairs] == ["1", "2"]
    assert pairs[0][1].content == "A"
    assert pairs[1][1].content == "B"
```

Run: `uv run pytest tests/unit/test_tool_executor.py -v`
Expected: 全部通过（4 passed）

- [ ] **Step 7: 接入 core/loop.py**

把 `AgentLoop.run()` 里原来的：

```python
            if response.stop_reason == "tool_use":
                for tc in response.tool_calls:
                    result = await invoke_tool(
                        self._registry, tc, self._bus, context.run_id,
                        permission_manager=self._permission_manager,
                        session_id=self._session_id,
                        hook_engine=self._hook_engine,
                    )
                    context.add_tool_result(tc.id, result.content, is_error=result.is_error)
```

替换为：

```python
            if response.stop_reason == "tool_use":
                from kivi_agent.core.tools.executor import execute_tool_batches, partition_tool_calls
                batches = partition_tool_calls(response.tool_calls, self._registry)
                pairs = await execute_tool_batches(
                    batches, self._registry, self._bus, context.run_id,
                    permission_manager=self._permission_manager,
                    session_id=self._session_id,
                    hook_engine=self._hook_engine,
                )
                for tc, result in pairs:
                    context.add_tool_result(tc.id, result.content, is_error=result.is_error)
```

- [ ] **Step 8: 全量回归**

Run: `uv run pytest tests/unit -v`
Expected: 全部通过（尤其关注 `test_loop.py`、`test_invocation.py` 这类既有工具调用相关测试，确认串行/并发切换后行为等价）

Run: `uv run ruff check src tests`
Run: `uv run mypy src`

- [ ] **Step 9: 提交**

```bash
git add src/kivi_agent/core/tools/executor.py src/kivi_agent/core/loop.py tests/unit/test_tool_executor.py
git commit -m "feat: 只读工具调用并发批次执行，接入 AgentLoop 主循环"
```

---

### Task B4: 工具动态搜索

**Files:**
- Modify: `src/kivi_agent/core/tools/registry.py`
- Create: `src/kivi_agent/core/tools/builtin/tool_search.py`
- Test: `tests/unit/test_tool_registry.py`（若不存在则新建）、`tests/unit/test_tool_search_tool.py`
- Modify: `src/kivi_agent/core/runner.py`
- Modify: `src/kivi_agent/core/permissions/policy.py`

**Interfaces:**
- Produces: `ToolRegistry.register(tool, *, deferred: bool = False)`、`ToolRegistry.search(query: str, limit: int = 5) -> list[BaseTool]`、`ToolRegistry.mark_discovered(name: str) -> None`、`ToolRegistry.tool_schemas()` 行为变化（默认跳过未发现的 deferred 工具）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_tool_registry.py
from __future__ import annotations

from kivi_agent.core.tools.builtin.read_file import ReadFileTool
from kivi_agent.core.tools.builtin.write_file import WriteFileTool
from kivi_agent.core.tools.registry import ToolRegistry


# 功能：验证 deferred=True 注册的工具默认不出现在 tool_schemas() 里
# 设计：这是"按需暴露"的核心行为——工具存在于 registry（get() 能查到），但不会被推给 LLM，
#      除非被 mark_discovered 过
def test_deferred_tool_hidden_from_schemas_until_discovered() -> None:
    registry = ToolRegistry()
    registry.register(WriteFileTool(), deferred=True)
    names = {s["name"] for s in registry.tool_schemas()}
    assert "write_file" not in names
    assert registry.get("write_file") is not None  # 仍然可以被直接调用（比如工具搜索到之后）


# 功能：验证 mark_discovered 之后，该工具出现在 tool_schemas() 里
# 设计：覆盖"发现后才暴露"这个状态迁移
def test_marking_discovered_exposes_schema() -> None:
    registry = ToolRegistry()
    registry.register(WriteFileTool(), deferred=True)
    registry.mark_discovered("write_file")
    names = {s["name"] for s in registry.tool_schemas()}
    assert "write_file" in names


# 功能：验证非 deferred（默认）注册的工具始终暴露，不受这套机制影响
# 设计：确保新增的 deferred 参数不改变现有工具（大多数都是默认注册）的既有行为
def test_non_deferred_tool_always_visible() -> None:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    names = {s["name"] for s in registry.tool_schemas()}
    assert "read_file" in names


# 功能：验证 search 按名字/描述关键词打分，名字命中排名优先于描述命中
# 设计：复用包 G 的 SkillLoader.search 同款打分逻辑，覆盖基本检索正确性
def test_registry_search_finds_by_keyword() -> None:
    registry = ToolRegistry()
    registry.register(ReadFileTool(), deferred=True)
    registry.register(WriteFileTool(), deferred=True)
    results = registry.search("write")
    assert len(results) == 1
    assert results[0].name == "write_file"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_tool_registry.py -v`
Expected: FAIL（`TypeError: register() got an unexpected keyword argument 'deferred'`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/tools/registry.py（完整替换）
from __future__ import annotations

from kivi_agent.core.tools.base import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._deferred: set[str] = set()
        self._discovered: set[str] = set()

    # 注册工具；deferred=True 时该工具默认不出现在 tool_schemas()，需先被 mark_discovered
    def register(self, tool: BaseTool, *, deferred: bool = False) -> None:
        self._tools[tool.name] = tool
        if deferred:
            self._deferred.add(tool.name)
        else:
            self._deferred.discard(tool.name)

    # 按名称查找工具，不存在返回 None（无论是否 deferred，都能直接查到）
    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    # 把一个 deferred 工具标记为已发现，之后会出现在 tool_schemas() 里
    def mark_discovered(self, name: str) -> None:
        self._discovered.add(name)

    # 返回当前应该暴露给 LLM 的工具 schema：非 deferred 工具 + 已发现的 deferred 工具
    def tool_schemas(self) -> list[dict[str, object]]:
        visible = [
            tool for name, tool in self._tools.items()
            if name not in self._deferred or name in self._discovered
        ]
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in visible
        ]

    # 按关键词搜索工具（不受 deferred 状态影响，搜索本身就是发现机制的一部分）：
    # 名字命中权重高于描述命中，按分数降序返回最多 limit 个
    def search(self, query: str, limit: int = 5) -> list[BaseTool]:
        q = query.strip().lower()
        if not q:
            return []
        scored: list[tuple[int, BaseTool]] = []
        for tool in self._tools.values():
            score = 0
            if q in tool.name.lower():
                score += 10
            if q in tool.description.lower():
                score += 5
            if score > 0:
                scored.append((score, tool))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [tool for _, tool in scored[:limit]]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_tool_registry.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 写 ToolSearchTool 的测试**

```python
# tests/unit/test_tool_search_tool.py
from __future__ import annotations

from kivi_agent.core.tools.builtin.tool_search import ToolSearchTool
from kivi_agent.core.tools.builtin.write_file import WriteFileTool
from kivi_agent.core.tools.registry import ToolRegistry


# 功能：验证调用 tool_search 后，匹配到的 deferred 工具被标记为已发现，随后出现在 tool_schemas 里
# 设计：这是"搜索即发现"这个约定的端到端验证——不只是返回搜索结果文本，
#      还要真的改变 registry 状态让工具变得可调用
async def test_tool_search_marks_results_as_discovered() -> None:
    registry = ToolRegistry()
    registry.register(WriteFileTool(), deferred=True)
    tool = ToolSearchTool(registry)

    result = await tool.invoke({"query": "write"})
    assert not result.is_error
    assert "write_file" in result.content
    assert "write_file" in {s["name"] for s in registry.tool_schemas()}
```

- [ ] **Step 6: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_tool_search_tool.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 7: 实现 ToolSearchTool**

```python
# src/kivi_agent/core/tools/builtin/tool_search.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.tools.base import BaseTool, ToolResult
from kivi_agent.core.tools.registry import ToolRegistry


class ToolSearchParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str


class ToolSearchTool(BaseTool):
    params_model = ToolSearchParams
    name = "tool_search"
    category = "read"
    description = (
        "Search for additional tools by keyword when the tool you need isn't in your "
        "current tool list. Matching tools become available for you to call immediately."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Keyword to search for."}},
        "required": ["query"],
    }

    # 注入 registry，用于搜索并标记发现的工具
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    # 搜索匹配工具，标记为已发现，返回名字+描述列表
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = ToolSearchParams.model_validate(params)
        results = self._registry.search(p.query)
        if not results:
            return ToolResult(content=f"no tools found matching: {p.query}")
        for tool in results:
            self._registry.mark_discovered(tool.name)
        lines = [f"{t.name}: {t.description}" for t in results]
        return ToolResult(content="\n".join(lines))
```

- [ ] **Step 8: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_tool_search_tool.py -v`
Expected: PASS（1 passed）

- [ ] **Step 9: 注册工具与权限策略、全量回归**

`policy.py`：`"tool_search": ToolPolicy(default=PermissionDecision.ALLOW),`

`runner.py::_build_registry()`（在构建完 registry 之后，返回之前）：

```python
if _ok("tool_search"):
    registry.register(ToolSearchTool(registry))
```

Run: `uv run pytest tests/unit -v`
Run: `uv run ruff check src tests`
Run: `uv run mypy src`
Expected: 全部通过

- [ ] **Step 10: 提交**

```bash
git add src/kivi_agent/core/tools/registry.py src/kivi_agent/core/tools/builtin/tool_search.py \
        tests/unit/test_tool_registry.py tests/unit/test_tool_search_tool.py \
        src/kivi_agent/core/runner.py src/kivi_agent/core/permissions/policy.py
git commit -m "feat: ToolRegistry 支持 deferred 工具与关键词搜索，新增 tool_search 工具"
```

---

## Self-Review Notes

- **覆盖范围**：B1 覆盖 M05（简化版，无远程探测）；B2 覆盖 M06；B3 覆盖 M07；B4 覆盖 M08。
- **与包 D 的耦合已在 Global Constraints 显式标注**：B3 依赖包 D 引入的 `BaseTool.category` 字段，包 D 已在 Wave 1 合入 `integration/wave1`，不存在时序风险。
- **类型一致性**：`execute_tool_batches` 返回类型 `list[tuple[ToolCallBlock, ToolResult]]`，`core/loop.py` 接入处按元组解包使用，命名与既有 `invoke_tool` 保持一致（不引入新的 Result 包装类型）。`ToolRegistry.register()` 新增的 `deferred` 关键字参数默认值 `False`，不破坏任何现有调用点（全仓库已有的 `registry.register(t)` 调用无需改动）。
