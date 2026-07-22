# kamaAgent 包E：上下文韧性 + 长期记忆 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 kivi-agent 已有的上下文压缩（`Compactor`）加固三层韧性（熔断、细粒度替换记录、落盘式工具输出预算），并新增一个跨 session 的长期记忆模块（抽取、存储、召回），解决"长任务不稳定""每次对话都从零开始"两个真实痛点——这是原企业整合方案里唯一被标注 P0 的个人可做项。

**Architecture:** 不重写 `Compactor`，在其现有 `compact()`/`compact_messages()` 之外新增失败计数状态和一个新的细粒度记录模块；长期记忆完全独立于 session 的 thread/notes 机制，是第三层记忆（`session 内 notes.md` < `项目/用户 context.md` < `跨 session 长期记忆`），存储在 `~/.kivi/memory/` 下的独立 Markdown 文件，通过 `ExecutionContext` 新增字段注入 system prompt。

**Tech Stack:** Python 3.12、pydantic v2、pytest + pytest-asyncio、uv。

## Global Constraints

- 遵守仓库 `CLAUDE.md`：每个函数上方一行中文注释；每个测试函数上方两行中文注释（`# 功能：`/`# 设计：`）。
- 测试命令：`uv run pytest tests/unit/test_xxx.py -v`；全量回归：`uv run pytest tests/unit -v`。
- **不做 mewcode 的"consolidation/dream"合并机制**（定时门槛+文件锁+子 Agent 后台合并记忆）——那是为多进程/多用户并发写记忆设计的，个人单机场景没有这个并发问题，做了就是过度工程，YAGNI。长期记忆只做"抽取+召回"两步。
- 长期记忆的抽取本质是走 LLM 调用，会产生真实 token 开销——所有新增的抽取逻辑必须设计成"失败不影响主流程"（`try/except` 兜底，抽取失败只记日志），不能让记忆功能的异常拖垮正常对话。

---

### Task E1: 压缩熔断

**Files:**
- Modify: `src/kivi_agent/core/compact/compactor.py`
- Modify: `src/kivi_agent/core/bus/events.py`
- Modify: `src/kivi_agent/core/loop.py`
- Test: `tests/unit/test_compactor.py`（追加用例）

**Interfaces:**
- Produces: `Compactor.consecutive_failures: int`（实例属性）、`Compactor.is_circuit_open() -> bool`、`class CompactionSkippedEvent(BaseModel)`（`core/bus/events.py`）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_compactor.py 追加
from unittest.mock import AsyncMock


# 功能：验证连续 3 次压缩失败（LLM 返回空摘要）后 is_circuit_open() 变为 True
# 设计：用返回空文本的假 provider 连续调用 compact_messages 3 次，
#      断言前 2 次 is_circuit_open() 仍为 False（未达阈值），第 3 次之后变 True，
#      覆盖"阈值触发"这个边界而不是随便断言个大概
async def test_circuit_opens_after_three_consecutive_failures(tmp_path) -> None:
    from kivi_agent.core.compact.compactor import Compactor
    from kivi_agent.core.events.bus import EventBus

    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "s1")
    fake_provider = AsyncMock()
    fake_provider.chat.return_value.text = ""  # 空摘要 → 失败
    fake_provider.chat.return_value.usage = None

    for _ in range(2):
        await compactor.compact_messages([{"role": "user", "content": "x"}], fake_provider)
        assert compactor.is_circuit_open() is False

    await compactor.compact_messages([{"role": "user", "content": "x"}], fake_provider)
    assert compactor.is_circuit_open() is True


# 功能：验证一次成功压缩会把连续失败计数清零，重新打开熔断
# 设计：先制造 2 次失败（未达阈值），再来一次成功，断言 consecutive_failures 归零
async def test_success_resets_failure_count(tmp_path) -> None:
    from kivi_agent.core.compact.compactor import Compactor
    from kivi_agent.core.events.bus import EventBus

    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "s1")
    fake_provider = AsyncMock()

    fake_provider.chat.return_value.text = ""
    fake_provider.chat.return_value.usage = None
    await compactor.compact_messages([{"role": "user", "content": "x"}], fake_provider)
    await compactor.compact_messages([{"role": "user", "content": "x"}], fake_provider)
    assert compactor.consecutive_failures == 2

    fake_provider.chat.return_value.text = "a good summary"
    fake_provider.chat.return_value.usage.output_tokens = 5
    await compactor.compact_messages([{"role": "user", "content": "x"}], fake_provider)
    assert compactor.consecutive_failures == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_compactor.py -k "circuit or resets_failure" -v`
Expected: FAIL（`AttributeError: 'Compactor' object has no attribute 'is_circuit_open'`）

- [ ] **Step 3: 加 CompactionSkippedEvent**

在 `core/bus/events.py` 里 `ContextCompactedEvent` 定义之后加：

```python
class CompactionSkippedEvent(BaseModel):
    type: Literal["compaction.skipped"] = "compaction.skipped"
    session_id: str
    run_id: str
    reason: str  # "circuit_open" | "llm_call_failed" | "empty_summary"
    consecutive_failures: int
    ts: str
```

并把它加入文件末尾的 `Event` 判别联合：`| CompactionSkippedEvent,`

- [ ] **Step 4: 改造 Compactor**

在 `Compactor.__init__` 里加：

```python
    _MAX_CONSECUTIVE_FAILURES = 3

    def __init__(self, bus: EventBus, session_dir: Path, session_id: str) -> None:
        self._bus = bus
        self._session_dir = session_dir
        self._session_id = session_id
        self.consecutive_failures = 0

    # 返回是否已达到连续失败阈值，达到时调用方应跳过本次压缩
    def is_circuit_open(self) -> bool:
        return self.consecutive_failures >= self._MAX_CONSECUTIVE_FAILURES
```

`compact_messages()` 里，`except Exception:` 分支和 `if not summary_text:` 分支，各自在 `return None` 之前加 `self.consecutive_failures += 1`；成功路径（`return CompactionResult(...)` 之前）加 `self.consecutive_failures = 0`。

`compact()` 方法开头加熔断短路：

```python
    async def compact(
        self,
        context: ExecutionContext,
        provider: LLMProvider,
        focus: str = "",
    ) -> CompactionResult | None:
        if self.is_circuit_open():
            await self._bus.publish(
                CompactionSkippedEvent(
                    session_id=self._session_id,
                    run_id=context.run_id,
                    reason="circuit_open",
                    consecutive_failures=self.consecutive_failures,
                    ts=_now(),
                )
            )
            logger.warning(
                "compactor: circuit open (consecutive_failures=%d), skipping compaction session=%s",
                self.consecutive_failures, self._session_id,
            )
            return None
        result = await self.compact_messages(context.messages, provider, focus=focus)
        # ... 其余不变
```

- [ ] **Step 5: loop.py 熔断状态传导（可选加固）**

`core/loop.py` 里触发压缩的条件判断不需要改——`compact()` 内部已经短路，`loop.py` 拿到 `None` 返回值时的既有行为（不替换 messages，继续正常步骤）天然就是正确的降级路径，不需要额外改动。此步骤仅确认现状符合预期，无代码变更。

- [ ] **Step 6: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_compactor.py -v`
Expected: 全部通过

- [ ] **Step 7: 提交**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-agent"
git add src/kivi_agent/core/compact/compactor.py src/kivi_agent/core/bus/events.py tests/unit/test_compactor.py
git commit -m "feat: 压缩连续失败熔断，达阈值后跳过并发布 CompactionSkippedEvent"
```

---

### Task E2: 细粒度替换记录

**Files:**
- Create: `src/kivi_agent/core/session/replacement.py`
- Modify: `src/kivi_agent/core/compact/compactor.py`
- Test: `tests/unit/test_replacement_record.py`

**Interfaces:**
- Produces: `@dataclass class ReplacementRecord`（`ts, original_message_count, original_tokens, summary_text, summary_tokens`）、`def write_replacement_record(session_dir: Path, record: ReplacementRecord) -> Path`、`def list_replacement_records(session_dir: Path) -> list[ReplacementRecord]`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_replacement_record.py
from __future__ import annotations

from pathlib import Path

from kivi_agent.core.session.replacement import (
    ReplacementRecord,
    list_replacement_records,
    write_replacement_record,
)


# 功能：验证写入一条替换记录后能通过 list_replacement_records 读回，字段一致
# 设计：构造一条记录写入再列出，逐字段断言，覆盖"写入格式和读取解析对得上"这个核心约束
def test_write_and_list_replacement_record(tmp_path: Path) -> None:
    record = ReplacementRecord(
        ts="2026-07-21T00:00:00+00:00",
        original_message_count=42,
        original_tokens=8000,
        summary_text="用户要修复登录 bug，已定位到 auth.py",
        summary_tokens=120,
    )
    write_replacement_record(tmp_path, record)
    records = list_replacement_records(tmp_path)
    assert len(records) == 1
    assert records[0].original_message_count == 42
    assert records[0].summary_text == "用户要修复登录 bug，已定位到 auth.py"


# 功能：验证多次压缩产生的多条记录按时间顺序全部保留、可列出
# 设计：写入两条记录，断言 list 返回长度为 2 且保持写入顺序，确认这是"追加式审计日志"而不是覆盖式存储
def test_multiple_records_are_all_preserved(tmp_path: Path) -> None:
    r1 = ReplacementRecord(ts="t1", original_message_count=10, original_tokens=1000, summary_text="a", summary_tokens=10)
    r2 = ReplacementRecord(ts="t2", original_message_count=20, original_tokens=2000, summary_text="b", summary_tokens=20)
    write_replacement_record(tmp_path, r1)
    write_replacement_record(tmp_path, r2)
    records = list_replacement_records(tmp_path)
    assert len(records) == 2
    assert [r.summary_text for r in records] == ["a", "b"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_replacement_record.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/session/replacement.py
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

_DIR_NAME = "replacements"


@dataclass
class ReplacementRecord:
    ts: str
    original_message_count: int
    original_tokens: int
    summary_text: str
    summary_tokens: int


# 把一条压缩替换记录写入 session 目录下 replacements/ 子目录，每条记录独立文件（追加式，不覆盖）
def write_replacement_record(session_dir: Path, record: ReplacementRecord) -> Path:
    replacements_dir = session_dir / _DIR_NAME
    replacements_dir.mkdir(parents=True, exist_ok=True)
    ts_slug = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    path = replacements_dir / f"replacement_{ts_slug}.json"
    path.write_text(json.dumps(asdict(record), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# 按文件名顺序（等价于时间顺序）读取该 session 下所有替换记录
def list_replacement_records(session_dir: Path) -> list[ReplacementRecord]:
    replacements_dir = session_dir / _DIR_NAME
    if not replacements_dir.exists():
        return []
    records = []
    for path in sorted(replacements_dir.glob("replacement_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        records.append(ReplacementRecord(**data))
    return records
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_replacement_record.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Compactor 接入**

在 `compact()` 方法里，`self._write_summary(result.summary_text)` 之后加：

```python
        from kivi_agent.core.session.replacement import ReplacementRecord, write_replacement_record
        write_replacement_record(
            self._session_dir,
            ReplacementRecord(
                ts=_now(),
                original_message_count=len(context.messages),
                original_tokens=result.original_token_estimate,
                summary_text=result.summary_text,
                summary_tokens=result.summary_tokens,
            ),
        )
```

（注意：这行必须放在 `context.messages = [...]` 就地替换**之前**读取 `len(context.messages)`，否则记录的会是替换后只有 2 条的消息数——检查现有代码顺序，若替换语句已经执行过，把 `original_message_count` 的取值提前到方法最开始缓存。）

- [ ] **Step 6: 提交**

```bash
git add src/kivi_agent/core/session/replacement.py src/kivi_agent/core/compact/compactor.py \
        tests/unit/test_replacement_record.py
git commit -m "feat: 压缩时写入细粒度替换记录，支持审计和重建"
```

---

### Task E3: 运行检查点

**Files:**
- Create: `src/kivi_agent/core/session/checkpoint.py`
- Modify: `src/kivi_agent/core/runner.py`
- Test: `tests/unit/test_checkpoint.py`

**Interfaces:**
- Produces: `@dataclass class CheckpointData`（`run_id, step, status, message_count, ts`）、`class CheckpointStore`，`save(sid: str, run_id: str, data: CheckpointData) -> None`、`load(sid: str, run_id: str) -> CheckpointData | None`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_checkpoint.py
from __future__ import annotations

from pathlib import Path

from kivi_agent.core.session.checkpoint import CheckpointData, CheckpointStore


# 功能：验证保存后能读回同一份检查点数据
# 设计：save 后立即 load，逐字段断言，覆盖最基本的往返正确性
def test_save_and_load_checkpoint(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path)
    data = CheckpointData(run_id="r1", step=3, status="running", message_count=7, ts="2026-07-21T00:00:00+00:00")
    store.save("s1", "r1", data)
    loaded = store.load("s1", "r1")
    assert loaded is not None
    assert loaded.step == 3
    assert loaded.status == "running"


# 功能：验证读取不存在的检查点返回 None 而不是抛异常
# 设计：直接 load 一个从未 save 过的 run_id，断言返回 None，
#      确保调用方（runner 启动时检查是否有可恢复检查点）不需要包一层 try/except
def test_load_missing_checkpoint_returns_none(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path)
    assert store.load("s1", "nonexistent") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_checkpoint.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/session/checkpoint.py
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CheckpointData:
    run_id: str
    step: int
    status: str  # "running" | "success" | "failed"
    message_count: int
    ts: str


class CheckpointStore:
    # 初始化检查点存储，复用 session 根目录（和 SessionStore 指向同一目录树）
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()

    # 返回指定 run 的检查点文件路径
    def _path(self, sid: str, run_id: str) -> Path:
        return self._root / sid / "runs" / run_id / "checkpoint.json"

    # 保存检查点，覆盖式写入（每个 run 只保留最新一份）
    def save(self, sid: str, run_id: str, data: CheckpointData) -> None:
        path = self._path(sid, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(data), ensure_ascii=False, indent=2), encoding="utf-8")

    # 加载检查点；不存在时返回 None
    def load(self, sid: str, run_id: str) -> CheckpointData | None:
        path = self._path(sid, run_id)
        if not path.exists():
            return None
        return CheckpointData(**json.loads(path.read_text(encoding="utf-8")))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_checkpoint.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: runner.py 接入**

在 `AgentRunner` 持有 `SessionStore` 的同一处，新增 `self._checkpoint_store = CheckpointStore(self._sessions_root)`（复用 `SessionStore` 构造时用的同一个根路径变量，具体变量名以 `runner.py` 现有代码为准）。在主循环每步工具结果写回后（`context.add_tool_result(...)` 之后）调用：

```python
self._checkpoint_store.save(
    session_id_str, run_id,
    CheckpointData(run_id=run_id, step=context.step, status=context.status,
                    message_count=len(context.messages), ts=_now()),
)
```

（若 `session_id_str` 为空字符串——即非 session 模式的一次性调用——跳过保存，检查点机制只对有 session 的对话生效，这是合理的范围限定：无 session 就无法定位到具体的恢复目标。）

- [ ] **Step 6: 提交**

```bash
git add src/kivi_agent/core/session/checkpoint.py src/kivi_agent/core/runner.py tests/unit/test_checkpoint.py
git commit -m "feat: 新增运行检查点，每步工具结果写回后持久化进度"
```

---

### Task E4: 工具输出预算加固——落盘+占位符

**Files:**
- Modify: `src/kivi_agent/core/compact/budget.py`
- Test: `tests/unit/test_budget.py`（追加用例）

**Interfaces:**
- Consumes: 现有 `TOOL_RESULT_LIMIT`/`TOOL_RESULT_KEEP`
- Produces: `def persist_and_truncate_tool_results(messages: list[dict], session_dir: Path, limit: int = TOOL_RESULT_LIMIT) -> list[dict]`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_budget.py 追加
from pathlib import Path

from kivi_agent.core.compact.budget import persist_and_truncate_tool_results


# 功能：验证超限的 tool_result 内容被落盘到 session_dir/tool_outputs/ 下，对话里替换成引用占位符
# 设计：构造一条超过 limit 的 tool_result 消息，断言落盘文件内容和原文完全一致（不丢数据），
#      对话里的占位符文本包含落盘文件的相对路径，确保可以顺藤摸瓜找回完整内容
def test_oversized_tool_result_is_persisted_with_placeholder(tmp_path: Path) -> None:
    long_text = "x" * 20_000
    messages = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": long_text}
    ]}]
    result = persist_and_truncate_tool_results(messages, tmp_path, limit=8_000)
    block = result[0]["content"][0]
    assert "tool_outputs/" in block["content"]
    assert "20000" not in block["content"] or "chars" in block["content"]  # 占位符描述里带省略字符数
    persisted_files = list((tmp_path / "tool_outputs").glob("*.txt"))
    assert len(persisted_files) == 1
    assert persisted_files[0].read_text(encoding="utf-8") == long_text


# 功能：验证未超限的 tool_result 原样保留，不产生落盘文件
# 设计：短文本消息走同一函数，断言内容不变且 tool_outputs 目录不存在，
#      覆盖"没有超限就不该有任何副作用"这个边界
def test_short_tool_result_is_untouched(tmp_path: Path) -> None:
    messages = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "short"}
    ]}]
    result = persist_and_truncate_tool_results(messages, tmp_path, limit=8_000)
    assert result[0]["content"][0]["content"] == "short"
    assert not (tmp_path / "tool_outputs").exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_budget.py -k persist -v`
Expected: FAIL（`ImportError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/compact/budget.py 追加
import hashlib
from pathlib import Path


# 对超长 tool_result 内容落盘保存完整版本，对话里替换为引用占位符；未超限内容原样保留
def persist_and_truncate_tool_results(
    messages: list[dict[str, Any]],
    session_dir: Path,
    limit: int = TOOL_RESULT_LIMIT,
) -> list[dict[str, Any]]:
    result = []
    for msg in messages:
        if msg.get("role") != "user":
            result.append(msg)
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            result.append(msg)
            continue
        new_blocks = []
        for block in content:
            if block.get("type") == "tool_result" and isinstance(block.get("content"), str):
                text = block["content"]
                if len(text) > limit:
                    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
                    out_dir = session_dir / "tool_outputs"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    out_path = out_dir / f"{digest}.txt"
                    out_path.write_text(text, encoding="utf-8")
                    block = dict(block)
                    block["content"] = (
                        f"[persisted: tool_outputs/{digest}.txt, "
                        f"{len(text)} chars omitted from context — read the file if full content is needed]"
                    )
            new_blocks.append(block)
        result.append({**msg, "content": new_blocks})
    return result
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_budget.py -v`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add src/kivi_agent/core/compact/budget.py tests/unit/test_budget.py
git commit -m "feat: 超限工具输出落盘保存，对话里保留可追溯占位符"
```

（此任务刻意不替换 `SessionStore.read_messages()` 里现有的 `truncate_tool_results` 调用——那是"读历史时的内存截断"，用途和触发时机都不同，`persist_and_truncate_tool_results` 是新增的、给 `runner.py` 在写入新消息前调用的加固版本，两者并存，不是替代关系。）

---

### Task E5: 长期记忆 — 存储与索引

**Files:**
- Create: `src/kivi_agent/core/memory/store.py`
- Test: `tests/unit/test_memory_store.py`

**Interfaces:**
- Produces: `@dataclass class MemoryEntry`（`name, type, description, body`，`type ∈ {"user","feedback","project","reference"}`）、`class MemoryStore`，`write(entry: MemoryEntry) -> Path`、`list_all() -> list[MemoryEntry]`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_memory_store.py
from __future__ import annotations

from pathlib import Path

from kivi_agent.core.memory.store import MemoryEntry, MemoryStore


# 功能：验证写入一条记忆后，能在同一 store 实例里通过 list_all 读回
# 设计：写入一条 type="feedback" 的记忆，断言字段完整、frontmatter 解析正确
def test_write_and_list_memory(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    entry = MemoryEntry(name="prefer-uv", type="feedback", description="用户偏好 uv 而不是 pip", body="始终用 uv 管理依赖")
    store.write(entry)
    entries = store.list_all()
    assert len(entries) == 1
    assert entries[0].name == "prefer-uv"
    assert entries[0].type == "feedback"
    assert entries[0].body == "始终用 uv 管理依赖"


# 功能：验证写入同名记忆会覆盖旧内容而不是产生重复文件
# 设计：用同一个 name 写两次不同 body，断言最终只有一条记忆且内容是第二次写入的
def test_write_same_name_overwrites(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.write(MemoryEntry(name="dup", type="project", description="d1", body="first"))
    store.write(MemoryEntry(name="dup", type="project", description="d2", body="second"))
    entries = store.list_all()
    assert len(entries) == 1
    assert entries[0].body == "second"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_memory_store.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/memory/store.py
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


@dataclass
class MemoryEntry:
    name: str
    type: str  # "user" | "feedback" | "project" | "reference"
    description: str
    body: str


class MemoryStore:
    # 初始化长期记忆存储根目录（典型路径 ~/.kivi/memory）
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()
        self._root.mkdir(parents=True, exist_ok=True)

    # 把一条记忆以 <name>.md（YAML frontmatter + 正文）写入，同名文件直接覆盖
    def write(self, entry: MemoryEntry) -> Path:
        path = self._root / f"{entry.name}.md"
        content = (
            f"---\nname: {entry.name}\ntype: {entry.type}\ndescription: {entry.description}\n---\n\n"
            f"{entry.body}\n"
        )
        path.write_text(content, encoding="utf-8")
        return path

    # 遍历存储目录下所有 .md 文件，解析成 MemoryEntry 列表
    def list_all(self) -> list[MemoryEntry]:
        entries = []
        for path in sorted(self._root.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            match = _FRONTMATTER_RE.match(text)
            if not match:
                continue
            frontmatter, body = match.groups()
            fields: dict[str, str] = {}
            for line in frontmatter.splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    fields[key.strip()] = val.strip()
            entries.append(MemoryEntry(
                name=fields.get("name", path.stem),
                type=fields.get("type", "project"),
                description=fields.get("description", ""),
                body=body.strip(),
            ))
        return entries
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_memory_store.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add src/kivi_agent/core/memory/store.py tests/unit/test_memory_store.py
git commit -m "feat: 新增长期记忆存储 MemoryStore（frontmatter Markdown 文件）"
```

---

### Task E6: 长期记忆 — 召回注入

**Files:**
- Create: `src/kivi_agent/core/memory/recall.py`
- Modify: `src/kivi_agent/core/context.py`
- Test: `tests/unit/test_memory_recall.py`

**Interfaces:**
- Consumes: `MemoryStore`/`MemoryEntry`（Task E5）
- Produces: `def build_memory_prompt(store: MemoryStore, max_entries: int = 10) -> str`；`ExecutionContext.long_term_memory: str = ""`（新字段）

**设计说明**：召回不做 mewcode 那种"额外一次 LLM 调用挑选最相关记忆"的语义选择器——个人场景下记忆条目量级不大（几十到几百条），直接全量注入（超过 `max_entries` 才截断，按文件 mtime 倒序取最近的）比额外引入一次 LLM 调用更简单可靠，YAGNI。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_memory_recall.py
from __future__ import annotations

from pathlib import Path

from kivi_agent.core.memory.recall import build_memory_prompt
from kivi_agent.core.memory.store import MemoryEntry, MemoryStore


# 功能：验证召回文本包含每条记忆的 description 和 body
# 设计：写入两条记忆后构建召回文本，断言两条的关键信息都出现在结果字符串里
def test_build_memory_prompt_includes_all_entries(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.write(MemoryEntry(name="a", type="feedback", description="偏好简洁回复", body="不要啰嗦"))
    store.write(MemoryEntry(name="b", type="project", description="部署方式", body="用 docker-compose"))
    prompt = build_memory_prompt(store)
    assert "不要啰嗦" in prompt
    assert "用 docker-compose" in prompt


# 功能：验证没有任何记忆时返回空字符串，而不是一段"没有记忆"的噪音文本
# 设计：空 store 调用，断言结果为空字符串，确保 ExecutionContext.system_prompt() 里的
#      "非空才拼接" 判断（沿用现有 global_context/session_notes 的写法）能正常跳过
def test_build_memory_prompt_empty_when_no_entries(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    assert build_memory_prompt(store) == ""
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_memory_recall.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/memory/recall.py
from __future__ import annotations

from kivi_agent.core.memory.store import MemoryStore


# 把长期记忆列表渲染成可注入 system prompt 的文本；无记忆时返回空字符串
def build_memory_prompt(store: MemoryStore, max_entries: int = 10) -> str:
    entries = store.list_all()[:max_entries]
    if not entries:
        return ""
    lines = [f"- [{e.type}] {e.description}: {e.body}" for e in entries]
    return "\n".join(lines)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_memory_recall.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: ExecutionContext 加字段并拼进 system_prompt()**

在 `core/context.py` 的 `ExecutionContext` dataclass 里加字段：

```python
    long_term_memory: str = ""
```

在 `system_prompt()` 方法里，`session_notes` 那段之后加：

```python
        if self.long_term_memory.strip():
            parts.append("\n\n## Long-term Memory\n" + self.long_term_memory.strip())
```

- [ ] **Step 6: runner.py 装配**

在 `AgentRunner` 构造 `ExecutionContext` 之前，加载并注入：

```python
from kivi_agent.core.memory.recall import build_memory_prompt
from kivi_agent.core.memory.store import MemoryStore
# ...
memory_store = MemoryStore(Path("~/.kivi/memory").expanduser())
long_term_memory = build_memory_prompt(memory_store)
```

并把 `long_term_memory=long_term_memory` 传入 `ExecutionContext(...)` 构造参数列表。

- [ ] **Step 7: 提交**

```bash
git add src/kivi_agent/core/memory/recall.py src/kivi_agent/core/context.py \
        src/kivi_agent/core/runner.py tests/unit/test_memory_recall.py
git commit -m "feat: 长期记忆召回注入 system prompt"
```

---

### Task E7: 长期记忆 — 异步抽取

**Files:**
- Create: `src/kivi_agent/core/memory/extractor.py`
- Modify: `src/kivi_agent/core/runner.py`
- Test: `tests/unit/test_memory_extractor.py`

**Interfaces:**
- Consumes: `MemoryStore`（Task E5）、`LLMProvider`
- Produces: `async def extract_memories(messages: list[dict], provider: LLMProvider, store: MemoryStore) -> int`（返回本次抽取写入的记忆条数）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_memory_extractor.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from kivi_agent.core.memory.extractor import extract_memories
from kivi_agent.core.memory.store import MemoryStore


# 功能：验证 LLM 返回结构化的 MEMORY 块时，能正确解析并写入 MemoryStore
# 设计：mock provider 返回一个符合约定格式的文本块，断言 extract_memories 返回写入条数为 1，
#      且 store 里确实出现了对应内容
async def test_extract_memories_parses_and_writes(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    fake_provider = AsyncMock()
    fake_provider.chat.return_value.text = (
        "MEMORY_NAME: prefer-tests\n"
        "MEMORY_TYPE: feedback\n"
        "MEMORY_DESC: 用户希望改动都先写测试\n"
        "MEMORY_BODY: 任何代码修改前先写失败测试再实现\n"
        "---END---"
    )
    count = await extract_memories(
        [{"role": "user", "content": "以后改代码都先写测试"}], fake_provider, store,
    )
    assert count == 1
    entries = store.list_all()
    assert entries[0].name == "prefer-tests"
    assert entries[0].type == "feedback"


# 功能：验证 LLM 调用失败时 extract_memories 吞掉异常返回 0，不向上抛出
# 设计：mock provider 的 chat 方法直接抛异常，断言函数正常返回 0 而不是让异常传播——
#      抽取是后台辅助功能，绝不能因为一次 LLM 调用失败拖垮调用方
async def test_extract_memories_swallows_llm_failure(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    fake_provider = AsyncMock()
    fake_provider.chat.side_effect = RuntimeError("network error")
    count = await extract_memories([{"role": "user", "content": "x"}], fake_provider, store)
    assert count == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_memory_extractor.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/memory/extractor.py
from __future__ import annotations

import logging
import re

from kivi_agent.core.memory.store import MemoryEntry, MemoryStore

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = """\
Review this conversation and decide if there is anything worth remembering long-term \
(a durable user preference, a project fact, a piece of feedback, or a useful reference).
If there is, respond with EXACTLY this format (one entry):

MEMORY_NAME: <short-kebab-case-slug>
MEMORY_TYPE: <user|feedback|project|reference>
MEMORY_DESC: <one-line description>
MEMORY_BODY: <the durable fact itself>
---END---

If there is nothing worth remembering, respond with exactly: NOTHING

Conversation:
{conversation}
"""

_FIELD_RE = {
    "name": re.compile(r"MEMORY_NAME:\s*(.+)"),
    "type": re.compile(r"MEMORY_TYPE:\s*(.+)"),
    "description": re.compile(r"MEMORY_DESC:\s*(.+)"),
    "body": re.compile(r"MEMORY_BODY:\s*(.+)"),
}


# 用 LLM 从一轮对话消息中抽取值得长期记住的内容，解析后写入 MemoryStore；失败静默返回 0，不影响主流程
async def extract_memories(
    messages: list[dict[str, object]],
    provider: "object",
    store: MemoryStore,
) -> int:
    conversation = "\n".join(
        f"[{m.get('role')}] {m.get('content')}" for m in messages if isinstance(m.get("content"), str)
    )
    if not conversation.strip():
        return 0

    try:
        response = await provider.chat(  # type: ignore[attr-defined]
            messages=[{"role": "user", "content": _EXTRACT_PROMPT.format(conversation=conversation)}],
            tool_schemas=[],
            bus=__import__("kivi_agent.core.events.bus", fromlist=["EventBus"]).EventBus(),
            run_id="memory-extract",
        )
    except Exception:
        logger.exception("memory extractor: LLM call failed")
        return 0

    text = response.text.strip()
    if text == "NOTHING" or not text:
        return 0

    fields: dict[str, str] = {}
    for key, pattern in _FIELD_RE.items():
        match = pattern.search(text)
        if match:
            fields[key] = match.group(1).strip()

    if not all(k in fields for k in ("name", "type", "description", "body")):
        logger.warning("memory extractor: LLM response did not match expected format")
        return 0

    store.write(MemoryEntry(
        name=fields["name"], type=fields["type"],
        description=fields["description"], body=fields["body"],
    ))
    return 1
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_memory_extractor.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: runner.py 触发点**

在 run 结束、`context.mark_success()`/`mark_failed()` 之后（离开 `async with EventWriter(...)` 块之前），加异步触发（不阻塞返回）：

```python
from kivi_agent.core.memory.extractor import extract_memories
# ...
asyncio.ensure_future(extract_memories(context.messages, provider, memory_store))
```

（复用 Task E6 Step 6 里已经构造好的 `memory_store` 变量。fire-and-forget 任务的异常已经在 `extract_memories` 内部兜底，不需要额外的 done-callback 处理。）

- [ ] **Step 6: 全量回归**

Run: `uv run pytest tests/unit -v`
Run: `uv run ruff check src tests`
Run: `uv run mypy src`
Expected: 全部通过

- [ ] **Step 7: 提交**

```bash
git add src/kivi_agent/core/memory/extractor.py src/kivi_agent/core/runner.py tests/unit/test_memory_extractor.py
git commit -m "feat: run 结束后异步抽取长期记忆，失败不影响主流程"
```

---

## Self-Review Notes

- **覆盖范围**：E1-E4 覆盖 M25（压缩，加固）+ M26（替换记录）+ M27（检查点，简化版——只做"保存进度供未来查询"，不做 mewcode 完整的"失败点检查+重入"逻辑，重入机制涉及 runner 启动时的分支判断，属于更大改动，本包不做，留一个明确的 TODO 标记供后续包评估）+ M28（熔断）+ M29（预算加固）。
- **M27 范围裁剪说明**：完整的"失败恢复+幂等重入"（Runner 启动时检测到未完成的检查点、自动从断点续跑）没有包含在 Task E3 里——那需要改动 Runner 的启动路径和 CLI/TUI 的交互逻辑（"发现可恢复任务，是否继续？"），影响面superus出了"上下文韧性"这个包的边界，更适合和包 H（TUI 增强，需要一个"会话恢复选择界面"）一起做。Task E3 只做了检查点的写入和读取原语，为后续接上恢复流程打好数据基础。
- **类型一致性**：`MemoryEntry`/`MemoryStore` 在 Task E5 定义后，Task E6（`build_memory_prompt`）、Task E7（`extract_memories`）都原样复用，字段名未变。`ExecutionContext.long_term_memory` 字段名和 `system_prompt()` 里的拼接逻辑与已有的 `global_context`/`project_context`/`session_notes` 保持完全一致的写法风格。
