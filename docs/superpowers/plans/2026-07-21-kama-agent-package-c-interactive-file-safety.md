# kamaAgent 包C（交互工具+文件安全）个人版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 kivi-agent 加三类能力：① M13 `ask_user` 交互工具，让 LLM 在长任务中途向用户提问并挂起等待回答；② M15 `FileStateCache` 文件状态缓存，让 `edit_file` 能检测"读完之后文件被外部修改"的过期情况；③ M16 `FileHistory` 文件历史快照，让每次编辑都留下可回滚的版本并支持 `rewind` 还原。

**Architecture:** `ask_user` 沿用 `PermissionManager.check_and_wait` 已验证的 `asyncio.Future` 模式——工具构造时持有一个 `QuestionStore`（与 `PermissionManager` 平级的薄包装），`invoke()` 创建 Future、发布事件、`await` Future、TUI 弹窗收集答案后 `respond()` 释放 Future。`FileStateCache` 是一个进程内单例（每 run 一份），`read_file` 读完后记录文件 mtime/size/sha256，`edit_file` 在做替换前先调用 `is_stale()` 校验，不通过则拒绝写入。`FileHistory` 类似 `git stash` 的简化版——每次 `edit_file` 提交前把当前内容快照到 `<project>/.kivi/file-history/<file>.<ts>.bak`，并提供一个 `rewind_file` 工具让 LLM 在发现"改坏了"时回滚到指定版本。三块能力都是对现有工具的旁路增强，不侵入 `core/loop.py` 也不修改 `invoke_tool()` 的既有契约。

**Tech Stack:** Python 3.12、pydantic v2、pytest + pytest-asyncio、Textual（TUI 弹窗用）、uv。

## Global Constraints

- 遵守仓库 `CLAUDE.md`：每个函数上方一行中文注释；每个测试函数上方两行中文注释（`# 功能：`/`# 设计：`）。
- 测试命令：`uv run pytest tests/unit/test_xxx.py -v`；全量回归：`uv run pytest tests/unit -v`；lint：`uv run ruff check src tests`；类型检查：`uv run mypy src`。
- 新工具必须在 `core/tools/builtin/` 下新建文件，继承 `core.tools.base.BaseTool`，实现 `name`、`description`、`input_schema`、`params_model`（pydantic `BaseModel`，`model_config = ConfigDict(extra="ignore")`）、`async def invoke(self, params: dict[str, object]) -> ToolResult`。
- 涉及路径的工具必须复用已有的目录穿越防护写法（`if ".." in Path(path_str).parts: raise PermissionError(...)`），保持和 `read_file.py`/`write_file.py`/`edit_file.py` 一致的安全边界。
- **合并锚点（必读，4 个并行 agent 都会触碰）**：`core/runner.py::_build_registry()` 和 `core/permissions/policy.py::DEFAULT_POLICIES` 是 4 个包 agent（包 B 工具搜索、包 C 交互/文件安全、包 D 计划模式/钩子、包 F 团队协调）都要修改的公共登记点。**新工具注册行上方必须加一行注释 `# <tool_name>（agent: package-c）`** 标识本包归属，方便第 1 波合并时按注释去重，不会出现"两个包都注册了 ask_user"的冲突。例如：
  ```python
  # ask_user（agent: package-c）
  if _ok("ask_user"):
      registry.register(AskUserTool(question_store, event_emitter=_emit_ask_user))
  ```
  `DEFAULT_POLICIES` 同样在每个新条目上方加一行：
  ```python
  # ask_user（agent: package-c）
  "ask_user": ToolPolicy(default=PermissionDecision.ASK),
  ```
- **edit_file.py 修改位置约束（必读）**：包 C 的 C5 任务要修改 `core/tools/builtin/edit_file.py` 接入 staleness 检查，**但基础闭环计划（`2026-07-20-kivi-agent-minimal-loop.md`）Task 4 的另一个 agent 也会改这个文件**（它定义了 `class EditFileTool` 和 `@staticmethod _atomic_write`）。两个 agent 并行执行时，包 C 的 C5 任务必须等基础闭环 Task 4 的 `_atomic_write` 方法落地后再做合并/集成，**新加的 staleness 检查方法 `_check_staleness` 放在 `edit_file.py` 里 `_atomic_write` 静态方法的下方**（文件位置明确），并在 `invoke()` 方法的早期（参数校验后、文件读取前）调用。这样第 1 波集成时按文件行号定位就能把两边的改动拼起来。
- **`ask_user` 挂起机制不重新发明**：直接复用 `PermissionManager.check_and_wait` 的 `asyncio.Future` 模式——`QuestionStore` 内部维护 `_pending: dict[str, asyncio.Future[str]]`，`wait_for_answer()` 创建 Future 并 `await` 它，`respond()` `set_result()` 释放它。这与 `PermissionManager` 的 `_pending` / `_PendingRequest` 字段几乎是 1:1 的同构关系，差别只是 `PermissionManager` 多了一层"deny/allow/ASK 分流"而 `QuestionStore` 只挂起一次问一次。TUI 端的弹窗组件（Task C2）以同样的方式订阅事件、发布决策消息、调用 `respond()`。

---

### Task C1: QuestionStore + ask_user 工具（Future 挂起机制）

**Files:**
- Create: `src/kivi_agent/core/tools/builtin/ask_user.py`
- Test: `tests/unit/test_ask_user_tool.py`

**Interfaces:**
- Produces: `class QuestionStore`（持 `_pending: dict[str, asyncio.Future[str]]` 和 `_counter`）、`class AskUserTool(BaseTool)`，`name = "ask_user"`，构造参数 `(question_store: QuestionStore, event_emitter: Callable | None = None)`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_ask_user_tool.py
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from kivi_agent.core.tools.builtin.ask_user import AskUserTool, QuestionStore


# 功能：验证 wait_for_answer 在 respond 之后返回用户的答案
# 设计：用一个 event_emitter 捕获 request_id，异步后台任务稍后调用 respond，
#      断言 wait_for_answer 的返回值就是 respond 给的字符串
async def test_wait_for_answer_returns_after_respond() -> None:
    store = QuestionStore()
    captured: dict[str, Any] = {}

    async def capture(event: dict[str, Any]) -> None:
        captured.update(event)

    async def respond_later() -> None:
        await asyncio.sleep(0.01)
        store.respond(captured["request_id"], "yes")

    task = asyncio.create_task(respond_later())
    answer = await store.wait_for_answer("q1", "Continue?", ["yes", "no"], event_emitter=capture)
    await task

    assert answer == "yes"
    assert captured["question"] == "Continue?"
    assert captured["options"] == ["yes", "no"]


# 功能：验证 AskUserTool 在 respond 之后返回的 ToolResult.content 包含用户答案
# 设计：通过 event_emitter 捕获 request_id，后台 respond 模拟"TUI 弹窗→用户点击"的端到端路径，
#      断言返回字符串里包含 yes，且 is_error=False
async def test_ask_user_tool_returns_answer() -> None:
    store = QuestionStore()
    captured: dict[str, Any] = {}

    async def capture(event: dict[str, Any]) -> None:
        captured.update(event)

    tool = AskUserTool(store, event_emitter=capture)

    async def respond_later() -> None:
        await asyncio.sleep(0.01)
        store.respond(captured["request_id"], "yes")

    task = asyncio.create_task(respond_later())
    result = await tool.invoke({"question": "Continue?", "options": ["yes", "no"]})
    await task

    assert not result.is_error
    assert "yes" in result.content


# 功能：验证 ask_user 接受 free-form 输入（options 为空列表）
# 设计：LLM 偶尔需要问开放式问题（"你偏好哪种风格？"），options=[] 时也要能挂起→应答→返回
async def test_ask_user_tool_free_form_answer() -> None:
    store = QuestionStore()
    captured: dict[str, Any] = {}

    async def capture(event: dict[str, Any]) -> None:
        captured.update(event)

    tool = AskUserTool(store, event_emitter=capture)

    async def respond_later() -> None:
        await asyncio.sleep(0.01)
        store.respond(captured["request_id"], "我偏好简洁回复")

    task = asyncio.create_task(respond_later())
    result = await tool.invoke({"question": "你偏好哪种风格？", "options": []})
    await task

    assert not result.is_error
    assert "我偏好简洁回复" in result.content


# 功能：验证重复对同一 request_id 调 respond 不会抛异常（幂等性）
# 设计：现实中 TUI 可能因重连/重发导致 respond 被调用两次，断言第二次是 no-op
#      而不是抛 InvalidStateError（future 已经被 set_result 过了）
async def test_respond_twice_is_noop() -> None:
    store = QuestionStore()
    fut: asyncio.Future[str] = asyncio.get_event_loop().create_future()
    store._pending["q1"] = fut  # type: ignore[attr-defined]
    store.respond("q1", "a")
    store.respond("q1", "b")  # 不应抛异常
    assert fut.result() == "a"


# 功能：验证对不存在的 request_id 调 respond 是安全 no-op
# 设计：TUI 断连重发时可能引用一个已经因超时被清理掉的 request_id，
#      不应因此让 daemon 崩溃
async def test_respond_unknown_request_is_noop() -> None:
    store = QuestionStore()
    store.respond("nonexistent", "a")  # 不应抛 KeyError
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_ask_user_tool.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'kivi_agent.core.tools.builtin.ask_user'`）

- [ ] **Step 3: 实现 QuestionStore + AskUserTool**

```python
# src/kivi_agent/core/tools/builtin/ask_user.py
from __future__ import annotations

import asyncio
import itertools
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.tools.base import BaseTool, ToolResult


# 事件 payload 形状：{"type": "ask_user.requested", "request_id": str, "question": str, "options": list[str]}
AskUserEventEmitter = Callable[[dict[str, Any]], Awaitable[None]]


# 维护 ask_user 工具的"问题→Future"映射，提供挂起/应答配对原语。
# 与 PermissionManager 共享 asyncio.Future 模式但只问一次，不做 ALLOW/DENY 分流。
class QuestionStore:
    def __init__(self) -> None:
        # request_id → Future[str]；respond() 时按 id 取出并 set_result
        self._pending: dict[str, asyncio.Future[str]] = {}
        # 单调递增的 id 计数器（避免引入 uuid 依赖，保持轻量）
        self._counter = itertools.count(1)

    # 生成下一个递增的 request_id（q1、q2、q3...）
    def _next_id(self) -> str:
        return f"q{next(self._counter)}"

    # 挂起直到 respond 被调用；可选地先发出事件让 TUI 弹窗
    async def wait_for_answer(
        self,
        request_id: str,
        question: str,
        options: list[str],
        event_emitter: AskUserEventEmitter | None = None,
    ) -> str:
        loop = asyncio.get_event_loop()
        future: asyncio.Future[str] = loop.create_future()
        self._pending[request_id] = future

        if event_emitter is not None:
            await event_emitter(
                {
                    "type": "ask_user.requested",
                    "request_id": request_id,
                    "question": question,
                    "options": list(options),
                }
            )

        return await future

    # 释放指定 request_id 的挂起 Future；id 不存在或 future 已 done 时均为 no-op
    def respond(self, request_id: str, answer: str) -> None:
        future = self._pending.pop(request_id, None)
        if future is None:
            return
        if not future.done():
            future.set_result(answer)

    # 取消指定 request_id 的挂起 Future（事件循环关闭/客户端断连时调用）
    def cancel(self, request_id: str) -> None:
        future = self._pending.pop(request_id, None)
        if future is None:
            return
        if not future.done():
            future.cancel()

    # 返回当前所有挂起的 request_id 列表（调试/测试用）
    def pending_ids(self) -> list[str]:
        return list(self._pending.keys())


class AskUserParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    question: str
    # 选项列表；空列表表示 free-form 输入（用户在弹窗里可以输入任意文本）
    options: list[str] = []


class AskUserTool(BaseTool):
    params_model = AskUserParams
    name = "ask_user"
    description = (
        "Ask the user a question and wait for their answer before continuing. "
        "Use this when you need clarification, a decision, or any input that "
        "cannot be inferred from the codebase. If `options` is provided, the user "
        "will be prompted to pick one (or type a custom response). If `options` "
        "is empty, the user can type a free-form answer. This call blocks until "
        "the user responds — do not use it for speculative questions."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The question to present to the user.",
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Optional list of suggested answers. "
                    "Empty array (default) means free-form input."
                ),
            },
        },
        "required": ["question"],
    }

    # 初始化：注入 QuestionStore（必填）和事件发射器（可选，runner 注入以连接 TUI）
    def __init__(
        self,
        question_store: QuestionStore,
        event_emitter: AskUserEventEmitter | None = None,
    ) -> None:
        super().__init__()
        self._questions = question_store
        self._emit = event_emitter

    # 挂起直到用户回答；返回内容直接是用户答案（包一层便于 LLM 解析）
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = AskUserParams.model_validate(params)
        request_id = self._questions._next_id()  # 复用 store 的 id 生成器
        answer = await self._questions.wait_for_answer(
            request_id=request_id,
            question=p.question,
            options=p.options,
            event_emitter=self._emit,
        )
        return ToolResult(content=f"User answered: {answer}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_ask_user_tool.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: lint + 类型检查**

Run: `uv run ruff check src/kivi_agent/core/tools/builtin/ask_user.py tests/unit/test_ask_user_tool.py`
Run: `uv run mypy src/kivi_agent/core/tools/builtin/ask_user.py`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-package-c-plan"
git add src/kivi_agent/core/tools/builtin/ask_user.py tests/unit/test_ask_user_tool.py
git commit -m "feat: 新增 QuestionStore + ask_user 工具（Future 挂起应答）"
```

---

### Task C2: TUI AskUserDialog Textual 组件

**Files:**
- Create: `src/kivi_agent/tui/ask_user_dialog.py`
- Test: `tests/unit/test_ask_user_dialog.py`

**Interfaces:**
- Produces: `class AskUserDialog(Static)`（Textual 组件），`class Answered(Message)`（携带 `request_id` 和 `answer`）；`mount_dialog(app, request_id, question, options, on_answer) -> AskUserDialog` 工厂函数

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_ask_user_dialog.py
from __future__ import annotations

from typing import Any

from kivi_agent.tui.ask_user_dialog import AskUserDialog


# 功能：验证选项数量 > 0 时，对话框渲染包含所有选项文本
# 设计：直接调 _render_ui 拿到富文本字符串，断言每个选项 label 都出现，
#      覆盖"渲染分支走的是 options 分支"这个关键路径
def test_render_includes_all_options() -> None:
    dlg = AskUserDialog("q1", "Continue?", ["yes", "no"])
    text = dlg._render_ui()
    assert "yes" in text
    assert "no" in text
    assert "Continue?" in text


# 功能：验证 free-form 模式（options 为空）渲染时提示"输入答案"而不是列出选项
# 设计：options=[] 时必须显示文本输入提示，否则用户在 TUI 看到空弹窗会困惑
def test_render_free_form_shows_input_prompt() -> None:
    dlg = AskUserDialog("q1", "你偏好哪种风格？", [])
    text = dlg._render_ui()
    assert "你偏好哪种风格？" in text
    assert "input" in text.lower() or "输入" in text


# 功能：验证 Answered 消息携带 request_id 和选中的选项
# 设计：直接调 _pick 模拟用户按数字键 1，断言 post_message 被调用且参数正确；
#      这里用 monkeypatch 替换 post_message 来捕获，避免起完整 App
def test_pick_emits_answered_message(monkeypatch: Any) -> None:
    dlg = AskUserDialog("q1", "Continue?", ["yes", "no"])
    captured: list[Any] = []
    monkeypatch.setattr(dlg, "post_message", lambda m: captured.append(m))

    dlg._pick("yes")

    assert len(captured) == 1
    msg = captured[0]
    assert msg.request_id == "q1"
    assert msg.answer == "yes"


# 功能：验证上下方向键改变 _cursor 索引并循环
# 设计：模拟两次 down 再 up，断言 _cursor 在 [0, 1, 2, 0, 1, ...] 范围内循环，
#      避免"光标到底就卡住"的边界 bug
def test_cursor_wraps_around() -> None:
    dlg = AskUserDialog("q1", "?", ["a", "b", "c"])
    assert dlg._cursor == 0
    dlg._move_cursor(+1)
    assert dlg._cursor == 1
    dlg._move_cursor(+1)
    assert dlg._cursor == 2
    dlg._move_cursor(+1)  # 越界回绕
    assert dlg._cursor == 0
    dlg._move_cursor(-1)  # 负向回绕
    assert dlg._cursor == 2
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_ask_user_dialog.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'kivi_agent.tui.ask_user_dialog'`）

- [ ] **Step 3: 实现 AskUserDialog**

```python
# src/kivi_agent/tui/ask_user_dialog.py
from __future__ import annotations

from textual import events
from textual.app import App, ComposeResult
from textual.message import Message
from textual.widgets import Input, Static


# 复用 TUI 现有的 PermissionSelect 风格（Static 子类 + Decided Message），
# 但题面渲染走 options / free-form 分支，提交方式有"选项"和"自由输入"两种
class AskUserDialog(Static):
    """内联 ask_user 弹窗：列出选项或提供输入框，用户决策后 post_message。"""

    can_focus = True

    DEFAULT_CSS = """
    AskUserDialog {
        height: auto;
        padding: 1 2;
        margin-bottom: 1;
        border: round cyan;
    }
    """

    # 用户作出选择时发布；app 负责把这个消息转成 IPC 回包调 question_store.respond()
    class Answered(Message):
        # 初始化 Answered 消息，存储 request_id 和答案字符串
        def __init__(self, widget: "AskUserDialog", request_id: str, answer: str) -> None:
            self.widget = widget
            self.request_id = request_id
            self.answer = answer
            super().__init__()

    # 初始化：保存 request_id、题面、选项列表，初始光标在第一项
    def __init__(self, request_id: str, question: str, options: list[str]) -> None:
        super().__init__("")
        self._request_id = request_id
        self._question = question
        self._options = list(options)
        self._cursor = 0
        self._input_widget: Input | None = None  # free-form 时挂的输入框

    def compose(self) -> ComposeResult:
        if self._options:
            yield Static(self._render_options(), classes="ask-user-options")
        else:
            self._input_widget = Input(placeholder="输入你的答案后按 enter")
            yield self._input_widget

    # 渲染 options 分支的富文本（光标高亮 + 快捷键提示）
    def _render_options(self) -> str:
        lines: list[str] = [f"[bold]?[/bold] {self._question}", ""]
        for i, opt in enumerate(self._options):
            if i == self._cursor:
                lines.append(f"  [bold cyan]❯ {i + 1}. {opt}[/bold cyan]")
            else:
                lines.append(f"    {i + 1}. {opt}")
        lines.append("[dim]  ↑↓ navigate   enter confirm   1-9 jump[/dim]")
        return "\n".join(lines)

    # 渲染 free-form 分支（compose 里直接挂 Input 控件，此处只返回题面文本）
    def _render_ui(self) -> str:
        if not self._options:
            return f"[bold]?[/bold] {self._question}\n[dim]  输入答案后按 enter[/dim]"
        return self._render_options()

    # 移动光标（+1 向下、-1 向上）；索引越界时回绕而不是夹紧
    def _move_cursor(self, delta: int) -> None:
        n = len(self._options)
        if n == 0:
            return
        self._cursor = (self._cursor + delta) % n
        self.update(self._render_options())

    # options 分支的键盘处理：方向键移动、数字键跳转、enter 确认
    def on_key(self, event: events.Key) -> None:
        if not self._options:
            return  # free-form 模式让 Input 控件自己处理
        key = event.key
        if key in ("up", "k"):
            event.stop()
            self._move_cursor(-1)
        elif key in ("down", "j"):
            event.stop()
            self._move_cursor(+1)
        elif key == "enter":
            event.stop()
            self._pick(self._options[self._cursor])
        elif key.isdigit():
            idx = int(key) - 1
            if 0 <= idx < len(self._options):
                event.stop()
                self._pick(self._options[idx])

    # Input 控件提交时（free-form 模式），从 Input.value 取答案并 post_message
    def on_input_submitted(self, event: Input.Submitted) -> None:
        answer = event.value.strip()
        if not answer:
            return
        self._pick(answer)

    # 把决策包成 Answered 消息发出；app 收到后会通过 IPC 调 question_store.respond()
    def _pick(self, answer: str) -> None:
        self.post_message(self.Answered(self, self._request_id, answer))


# 工厂函数：在 app 里挂一个 AskUserDialog 到 prompt 上方，并把 on_answer 回调挂上。
# 单独抽出来方便在 Answered 消息里直接调 app.call_later / run_worker 转发。
def mount_dialog(
    app: App[None],
    request_id: str,
    question: str,
    options: list[str],
) -> AskUserDialog:
    dlg = AskUserDialog(request_id, question, options)
    app.mount(dlg, before="#prompt")
    dlg.focus()
    return dlg
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_ask_user_dialog.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-package-c-plan"
git add src/kivi_agent/tui/ask_user_dialog.py tests/unit/test_ask_user_dialog.py
git commit -m "feat: 新增 TUI AskUserDialog 弹窗（options + free-form 双模式）"
```

---

### Task C3: ask_user 接入 runner + 权限策略 + bus 事件

**Files:**
- Modify: `src/kivi_agent/core/runner.py`（在 `_build_registry` 里注册 `AskUserTool`，加 `# ask_user（agent: package-c）` 锚点注释）
- Modify: `src/kivi_agent/core/permissions/policy.py::DEFAULT_POLICIES`（登记 `ask_user` 策略 + 在 `_PREVIEW_KEY` 加预览字段）
- Modify: `src/kivi_agent/core/permissions/manager.py`（让 `eval_ask_user_tools` 走挂起路径——ask_user 总是 ASK，所以默认就落进 `await future`；**不需要改 manager**）
- Modify: `src/kivi_agent/core/bus/events.py`（加 `AskUserRequestedEvent`，并把 `Event` 联合加上）
- Modify: `src/kivi_agent/tui/app.py`（订阅 `ask_user.requested` 事件，调 `mount_dialog`，监听 `Answered` 消息并通过 IPC 回包到 `question_store.respond()`）
- Test: `tests/unit/test_runner.py`（追加用例，验证 ask_user 被注册到 registry）

**Interfaces:**
- Produces: `class AskUserRequestedEvent(BaseModel)`（`type: Literal["ask_user.requested"]`、字段 `run_id, request_id, question, options, session_id, ts`）；`AgentRunner.__init__` 接受可选 `question_store: QuestionStore | None = None`

**设计说明**：和 `PermissionManager.check_and_wait` 完全同构——`ask_user` 工具构造时拿到 `QuestionStore` 引用，`invoke()` 调 `wait_for_answer()` 创建 Future 并 `await`，事件通过 bus 发到 TUI，TUI 弹窗后用 `question_store.respond(request_id, answer)` 释放 Future。因为 `ask_user` 在 `DEFAULT_POLICIES` 里是 `ASK`，permission 那一层就会在 tool 执行前先把"是否允许问用户"这个动作挂起一次（用户也可能拒绝这次提问本身），再轮到工具内的 Future 挂起等答案——两层 Future 嵌套但语义清晰：外层是"你同意 Agent 问问题吗"，内层是"Agent 问的问题你答什么"。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_runner.py 追加
from kivi_agent.core.tools.builtin.ask_user import AskUserTool, QuestionStore


# 功能：验证 runner._build_registry 在传入 question_store 时把 ask_user 注册进 registry
# 设计：用最小可行配置构造 runner，断言 registry.get("ask_user") 返回非 None 且 name 正确，
#      覆盖"runner 装配 ask_user 工具"这条主干路径
def test_build_registry_registers_ask_user(tmp_path) -> None:
    from kivi_agent.core.config import KamaConfig
    from kivi_agent.core.runner import AgentRunner
    from kivi_agent.core.task.manager import TaskManager
    from pathlib import Path as _Path

    config = KamaConfig()
    runner = AgentRunner(config, runs_dir=tmp_path)
    question_store = QuestionStore()
    registry = runner._build_registry(
        TaskManager(tmp_path / ".tasks"),
        question_store=question_store,
    )
    tool = registry.get("ask_user")
    assert tool is not None
    assert tool.name == "ask_user"
    assert isinstance(tool, AskUserTool)


# 功能：验证 tool_whitelist 不包含 ask_user 时该工具不会被注册
# 设计：whitelist=["bash"] 时调 _build_registry，断言 registry.get("ask_user") 为 None，
#      覆盖"白名单过滤对 ask_user 也生效"这条一致性约束
def test_build_registry_respects_whitelist_for_ask_user(tmp_path) -> None:
    from kivi_agent.core.config import KamaConfig
    from kivi_agent.core.runner import AgentRunner
    from kivi_agent.core.task.manager import TaskManager

    config = KamaConfig()
    runner = AgentRunner(config, runs_dir=tmp_path)
    question_store = QuestionStore()
    registry = runner._build_registry(
        TaskManager(tmp_path / ".tasks"),
        question_store=question_store,
        tool_whitelist=["bash"],
    )
    assert registry.get("ask_user") is None
    assert registry.get("bash") is not None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_runner.py -k ask_user -v`
Expected: FAIL（`_build_registry` 不接受 `question_store` 参数，抛出 `TypeError`）

- [ ] **Step 3: bus events 加 AskUserRequestedEvent**

在 `src/kivi_agent/core/bus/events.py` 末尾追加（`PermissionDeniedEvent` 之后）：

```python
class AskUserRequestedEvent(BaseModel):
    type: Literal["ask_user.requested"] = "ask_user.requested"
    run_id: str
    request_id: str
    question: str
    options: list[str]
    session_id: str
    ts: str
```

并在 `Event` Annotated 联合里 `PermissionDeniedEvent` 之后插入 `| AskUserRequestedEvent`：

```python
Event = Annotated[
    CoreStartedEvent
    | RunStartedEvent
    ...
    | PermissionDeniedEvent
    | AskUserRequestedEvent
    | SubagentStartedEvent
    ...
]
```

- [ ] **Step 4: 改造 runner.py**

在 `core/runner.py` 顶部 `from kivi_agent.core.tools.builtin import (...)` 块里加 `AskUserTool`：

```python
from kivi_agent.core.tools.builtin import (
    AskUserTool,
    BashTool,
    ListDirTool,
    NoteSaveTool,
    ReadFileTool,
    TaskCreateTool,
    TaskGetTool,
    TaskListTool,
    TaskUpdateTool,
    WriteFileTool,
)
```

再加一行 import：

```python
from kivi_agent.core.tools.builtin.ask_user import QuestionStore
```

在 `AgentRunner.__init__` 末尾加：

```python
        # 跨 run 共享的 ask_user 问题挂起注册表（所有 ask_user 工具共用同一份，
        # 这样 spawn_agent 子 run 也能复用主 run 的 TUI 弹窗通道）
        self._question_store = question_store or QuestionStore()
```

并把 `__init__` 签名改为：

```python
    def __init__(
        self,
        config: KamaConfig,
        *,
        ...
        permission_manager: PermissionManager | None = None,
        question_store: QuestionStore | None = None,
        mcp_manager: McpServerManager | None = None,
    ) -> None:
```

在 `_build_registry` 签名加 `question_store` 参数（默认 `None`）：

```python
    def _build_registry(
        self,
        task_manager: TaskManager,
        *,
        session: Session | None = None,
        store: SessionStore | None = None,
        run_id: str | None = None,
        provider: LLMProvider | None = None,
        bus: EventBus | None = None,
        child_runs_dir: Path | None = None,
        session_id: str = "",
        tool_whitelist: list[str] | None = None,
        question_store: QuestionStore | None = None,
    ) -> ToolRegistry:
```

在 `_build_registry` 末尾（`return registry` 之前）插入 ask_user 注册段，**带锚点注释**：

```python
        # ask_user（agent: package-c）
        qs = question_store if question_store is not None else self._question_store
        if _ok("ask_user"):
            async def _emit_ask_user(event: dict[str, Any]) -> None:
                if bus is None:
                    return
                await bus.publish(
                    AskUserRequestedEvent(
                        run_id=run_id or "",
                        request_id=str(event.get("request_id", "")),
                        question=str(event.get("question", "")),
                        options=list(event.get("options", []) or []),
                        session_id=session_id,
                        ts=_now(),
                    )
                )
            registry.register(AskUserTool(qs, event_emitter=_emit_ask_user))
```

顶部 import 区域加 `AskUserRequestedEvent`：

```python
from kivi_agent.core.bus.events import (
    AskUserRequestedEvent,
    RunFinishedEvent,
    RunStartedEvent,
)
```

并在 `run_and_capture` 里调 `_build_registry(...)` 处补 `question_store=self._question_store`：

```python
                registry = self._build_registry(
                    task_manager,
                    session=session,
                    store=store,
                    run_id=run_id,
                    provider=provider,
                    bus=bus,
                    child_runs_dir=child_runs_dir,
                    session_id=session_id_str,
                    tool_whitelist=tool_whitelist,
                    question_store=self._question_store,
                )
```

- [ ] **Step 5: policy.py 登记 ask_user 策略**

在 `src/kivi_agent/core/permissions/policy.py` 的 `DEFAULT_POLICIES` 字典里加：

```python
DEFAULT_POLICIES: dict[str, ToolPolicy] = {
    "bash":       ToolPolicy(default=PermissionDecision.ASK),
    "write_file": ToolPolicy(default=PermissionDecision.ASK),
    "read_file":  ToolPolicy(default=PermissionDecision.ALLOW),
    "list_dir":   ToolPolicy(default=PermissionDecision.ALLOW),
    "note_save":  ToolPolicy(default=PermissionDecision.ALLOW),
    # ask_user（agent: package-c）
    "ask_user":   ToolPolicy(default=PermissionDecision.ASK),
}
```

并在 `_PREVIEW_KEY` 加预览字段：

```python
_PREVIEW_KEY: dict[str, str] = {
    "bash":       "command",
    "read_file":  "path",
    "write_file": "path",
    "list_dir":   "path",
    "note_save":  "content",
    "ask_user":   "question",
}
```

- [ ] **Step 6: TUI app.py 监听 ask_user.requested 并回包**

在 `src/kivi_agent/tui/app.py` 的事件订阅 `topics` 列表里追加 `"ask_user.*"`：

```python
            params: dict[str, Any] = {
                "topics": [
                    "session.*",
                    "run.*",
                    "step.*",
                    "tool.*",
                    "llm.token",
                    "llm.usage",
                    "log.*",
                    "permission.*",
                    "ask_user.*",
                    "context.*",
                    "subagent.*",
                    "skill.*",
                ],
                "scope": "global",
            }
```

在 `_handle_event_inner` 里 `permission.requested` 处理分支之后追加：

```python
        elif t == "ask_user.requested":
            request_id = event.get("request_id", "")
            question = event.get("question", "")
            options = list(event.get("options", []) or [])
            mount_dialog(self, request_id, question, options)
            # Answered 消息由下面的 on_ask_user_dialog_answered 接收
```

并在 `KamaTuiApp` 类里加一个 `on_ask_user_dialog_answered` 消息处理方法（与现有 `on_permission_select_decided` 风格一致）：

```python
    # 处理 AskUserDialog.Answered 消息：通过 IPC 把答案送回 daemon 端 question_store
    def on_ask_user_dialog_answered(self, msg: "AskUserDialog.Answered") -> None:  # type: ignore[name-defined]
        try:
            if self._client is not None:
                asyncio.create_task(self._client.send_command(
                    "ask_user.respond",
                    {"request_id": msg.request_id, "answer": msg.answer},
                ))
            msg.widget.remove()
            prompt = self._prompt()
            if prompt is not None:
                prompt.focus()
        except Exception:
            log.exception("on_ask_user_dialog_answered failed request_id=%s", msg.request_id)
```

（Textual 的 `on_<widget_class>_<message_class>` 自动路由机制会让 `AskUserDialog.Answered` 消息触发这个方法，与现有 `on_permission_select_decided` 完全同构。）

并加 import：

```python
from kivi_agent.tui.ask_user_dialog import AskUserDialog, mount_dialog
```

- [ ] **Step 7: 运行测试 + 全量回归**

Run: `uv run pytest tests/unit/test_runner.py -k ask_user -v`
Expected: PASS（2 passed）

Run: `uv run pytest tests/unit/test_ask_user_tool.py tests/unit/test_ask_user_dialog.py -v`
Expected: 全部通过

Run: `uv run pytest tests/unit -v`
Expected: 全部通过（确认 ask_user 接入没有破坏既有测试）

Run: `uv run ruff check src tests`
Run: `uv run mypy src`
Expected: 全部通过

- [ ] **Step 8: 提交**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-package-c-plan"
git add src/kivi_agent/core/runner.py src/kivi_agent/core/permissions/policy.py \
        src/kivi_agent/core/bus/events.py src/kivi_agent/tui/app.py \
        tests/unit/test_runner.py
git commit -m "feat: ask_user 接入 runner/policy/bus/TUI（带 package-c 锚点注释）"
```

---

### Task C4: FileStateCache 数据类 + read_file 记录

**Files:**
- Create: `src/kivi_agent/core/tools/file_state_cache.py`
- Test: `tests/unit/test_file_state_cache.py`
- Modify: `src/kivi_agent/core/tools/builtin/read_file.py`（在读取成功后调 `cache.record(path)`）

**Interfaces:**
- Produces: `@dataclass class FileState`（`path: str, mtime: float, size: int, sha256: str | None`）、`class FileStateCache`（`record(path) -> FileState`、`is_stale(path) -> bool`、`invalidate(path) -> None`、`has(path) -> bool`）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_file_state_cache.py
from __future__ import annotations

from pathlib import Path

from kivi_agent.core.tools.file_state_cache import FileStateCache


# 功能：验证 record 后 is_stale 返回 False（未变化）
# 设计：写文件→record→is_stale，覆盖"刚记录就检查"这条基线
def test_record_then_is_stale_returns_false(tmp_path: Path) -> None:
    cache = FileStateCache()
    f = tmp_path / "x.txt"
    f.write_text("hello")
    cache.record(f)
    assert cache.has(f) is True
    assert cache.is_stale(f) is False


# 功能：验证文件被外部修改后 is_stale 返回 True
# 设计：record 后改写文件内容，断言 is_stale=True，覆盖"检测到变化"这条核心路径
def test_is_stale_detects_modification(tmp_path: Path) -> None:
    cache = FileStateCache()
    f = tmp_path / "x.txt"
    f.write_text("hello")
    cache.record(f)
    f.write_text("modified content that is different")
    assert cache.is_stale(f) is True


# 功能：验证从未 record 过的文件 is_stale 返回 False（默认视为新鲜）
# 设计：edit_file 在没有 read_file 记录的情况下不应该误报 stale；
#      这条规则保护"我直接编辑一个新文件"的合法用例
def test_unrecorded_file_is_not_stale(tmp_path: Path) -> None:
    cache = FileStateCache()
    f = tmp_path / "never_read.txt"
    f.write_text("hello")
    assert cache.has(f) is False
    assert cache.is_stale(f) is False


# 功能：验证 invalidate 后 is_stale 重新返回 False（清掉旧记录）
# 设计：覆盖"显式让缓存忘记这个文件"的语义，read_file 失败/重读时调用
def test_invalidate_clears_record(tmp_path: Path) -> None:
    cache = FileStateCache()
    f = tmp_path / "x.txt"
    f.write_text("hello")
    cache.record(f)
    f.write_text("modified")
    assert cache.is_stale(f) is True
    cache.invalidate(f)
    assert cache.has(f) is False
    assert cache.is_stale(f) is False


# 功能：验证文件被删除后再 record 能正确捕获新的不存在状态
# 设计：record 一个文件，删除它，再 record 同一个 path（cache 内部调 stat），
#      断言不抛异常且 size=0 / 不存在标记
def test_record_handles_missing_file(tmp_path: Path) -> None:
    cache = FileStateCache()
    f = tmp_path / "ghost.txt"
    f.write_text("hello")
    cache.record(f)
    f.unlink()
    # missing path 不抛 FileNotFoundError，记录 size=0 标记"曾经存在但现在不在"
    state = cache.record(f)
    assert state.size == 0
    assert cache.is_stale(f) is True  # size 从 5 变 0 → 视为过期
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_file_state_cache.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 FileStateCache**

```python
# src/kivi_agent/core/tools/file_state_cache.py
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

# 超过这个大小不计算 sha256（避免大文件每次读都哈希一遍 O(n)）；
# 仅用 mtime + size 检测，对超大文件足够（误报概率极低）
_SHA256_SIZE_LIMIT = 1 * 1024 * 1024  # 1 MB


@dataclass
class FileState:
    path: str
    mtime: float  # POSIX timestamp（path.stat().st_mtime）
    size: int
    sha256: str | None  # None 表示文件过大未计算


# 进程内文件状态缓存：read_file 写、edit_file 读，检测"读后改"过期情况。
# 不做持久化（每个 run / 每次启动重建），不做并发控制（单 event loop 串行调用）。
class FileStateCache:
    def __init__(self) -> None:
        # path（字符串，绝对路径）→ 最近一次 record 时的状态
        self._states: dict[str, FileState] = {}

    # 规范化 path 为绝对字符串键，避免相对/绝对混用导致同一文件被记两次
    @staticmethod
    def _key(path: Path) -> str:
        return str(path.resolve())

    # 读取 path 当前状态并存入缓存；文件不存在时记一个 size=0 的"墓碑"状态
    def record(self, path: Path) -> FileState:
        key = self._key(path)
        try:
            stat = path.stat()
        except FileNotFoundError:
            state = FileState(path=key, mtime=0.0, size=0, sha256=None)
            self._states[key] = state
            return state

        sha: str | None = None
        if stat.st_size <= _SHA256_SIZE_LIMIT:
            sha = hashlib.sha256(path.read_bytes()).hexdigest()

        state = FileState(path=key, mtime=stat.st_mtime, size=stat.st_size, sha256=sha)
        self._states[key] = state
        return state

    # 是否曾记录过这个 path（has 是 is_stale 反向查询的前置检查）
    def has(self, path: Path) -> bool:
        return self._key(path) in self._states

    # 检测 path 当前状态与缓存中是否一致；
    # 未记录过返回 False（视为新鲜，避免无前置 read 时误报）
    def is_stale(self, path: Path) -> bool:
        key = self._key(path)
        recorded = self._states.get(key)
        if recorded is None:
            return False
        try:
            current = path.stat()
        except FileNotFoundError:
            return recorded.size != 0  # 之前有现在没了 → 过期

        if current.st_size != recorded.size:
            return True
        # mtime 精确到秒就够用——同秒内写两次的概率极低
        if current.st_mtime != recorded.mtime:
            return True
        # mtime + size 一致但内容确实被改过的极端情况（秒内覆写），用 sha256 再校一次
        if recorded.sha256 is not None and recorded.size <= _SHA256_SIZE_LIMIT:
            current_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if current_sha != recorded.sha256:
                return True
        return False

    # 从缓存中删除 path（read_file 失败/显式重读时调用）
    def invalidate(self, path: Path) -> None:
        self._states.pop(self._key(path), None)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_file_state_cache.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: read_file 接入 record**

修改 `src/kivi_agent/core/tools/builtin/read_file.py`，把 `ReadFileTool` 改为可注入 cache，并把 `record` 调用放在读取成功后：

```python
# src/kivi_agent/core/tools/builtin/read_file.py
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.tools.base import BaseTool, ToolResult
from kivi_agent.core.tools.file_state_cache import FileStateCache

_MAX_BYTES = 512 * 1024  # 512 KB


class ReadFileParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str


class ReadFileTool(BaseTool):
    params_model = ReadFileParams
    name = "read_file"
    description = (
        "Read the text content of a file. "
        "Path must be relative to the current working directory. "
        "Files larger than 512 KB are truncated."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file (relative to current working directory).",
            }
        },
        "required": ["path"],
    }

    # 初始化：注入可选的 FileStateCache；不传时跳过记录（不破坏现有调用方）
    def __init__(self, file_state_cache: FileStateCache | None = None) -> None:
        super().__init__()
        self._cache = file_state_cache

    # 读取文件内容；超 512KB 截断；禁止 .. 路径遍历；读成功后写入 FileStateCache
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        path_str = ReadFileParams.model_validate(params).path

        if ".." in Path(path_str).parts:
            raise PermissionError(f"path traversal not allowed: {path_str}")

        path = Path(path_str)
        raw = path.read_bytes()  # raises FileNotFoundError if absent
        truncated = len(raw) > _MAX_BYTES
        text = raw[:_MAX_BYTES].decode("utf-8", errors="replace")
        if truncated:
            text += "\n[truncated]"

        # 读成功后再记——失败不污染缓存
        if self._cache is not None:
            self._cache.record(path)

        return ToolResult(content=text)
```

- [ ] **Step 6: 全量回归确认未破坏现有 read_file 测试**

Run: `uv run pytest tests/unit/test_read_file.py tests/unit/test_file_state_cache.py -v`
Expected: 全部通过（test_read_file 现有 6 个用例因新增可选构造参数仍兼容——它们都写 `ReadFileTool()` 不传 cache）

- [ ] **Step 7: 提交**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-package-c-plan"
git add src/kivi_agent/core/tools/file_state_cache.py \
        src/kivi_agent/core/tools/builtin/read_file.py \
        tests/unit/test_file_state_cache.py
git commit -m "feat: 新增 FileStateCache 文件状态缓存（mtime+size+sha256）"
```

---

### Task C5: edit_file 接入 staleness 检查

**Files:**
- Modify: `src/kivi_agent/core/tools/builtin/edit_file.py`（在 `_atomic_write` 静态方法**下方**追加 `_check_staleness` 方法；`invoke()` 早期调用一次）
- Modify: `src/kivi_agent/core/runner.py`（把 `FileStateCache` 注入 `ReadFileTool` 和 `EditFileTool`，两个工具共享同一份 cache）
- Test: `tests/unit/test_edit_file_tool.py`（追加 2 个用例：cache 未注入时不做检查、cache 注入时检测到过期则返回错误）

**Interfaces:**
- Produces: `EditFileTool(file_state_cache: FileStateCache | None = None)`（构造参数），`EditFileTool._check_staleness(path: Path) -> ToolResult | None`（不通过时返回带 `error_type="stale_file"` 的错误 ToolResult）

**设计说明**：见 Global Constraints 中的 "edit_file.py 修改位置约束"——本任务的 `_check_staleness` 方法在源文件里追加在已有 `_atomic_write` 静态方法下面，**调用点放在 `invoke()` 方法里"参数校验后、文件读取前"**（参数校验抛 `PermissionError` 优先于 staleness，避免路径穿越检测被文件状态盖掉）。`is_stale()` 在没 record 过的文件上返回 False，所以"没读过就 edit"这条合法路径仍能正常工作。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_edit_file_tool.py 追加
from kivi_agent.core.tools.file_state_cache import FileStateCache


# 功能：验证未注入 cache 时 edit_file 不做 staleness 检查（不破坏现有行为）
# 设计：用现有 4 个用例之一的写入模式编辑文件，不传 cache，断言 is_error=False，
#      覆盖"可选 cache 不影响默认路径"
async def test_edit_without_cache_works(tmp_path) -> None:
    from kivi_agent.core.tools.builtin.edit_file import EditFileTool

    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    tool = EditFileTool()  # 不传 cache
    result = await tool.invoke({"path": str(f), "old_string": "x = 1", "new_string": "x = 2"})
    assert not result.is_error
    assert f.read_text() == "x = 2\n"


# 功能：验证注入 cache 后文件被外部修改时 edit_file 拒绝并返回 stale_file 错误
# 设计：先 read_file 记录状态，再让外部脚本改写文件，再调 edit_file，
#      断言返回 is_error=True 且 error_type="stale_file"，文件内容未变
async def test_edit_detects_stale_file(tmp_path) -> None:
    from kivi_agent.core.tools.builtin.edit_file import EditFileTool
    from kivi_agent.core.tools.builtin.read_file import ReadFileTool

    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    cache = FileStateCache()
    # 1) read_file 记录状态
    await ReadFileTool(cache).invoke({"path": str(f)})
    assert cache.has(f) is True
    # 2) 外部脚本改写文件（模拟另一个进程/编辑器/用户手动编辑）
    f.write_text("x = 999\n")
    # 3) edit_file 应该检测到过期并拒绝
    result = await EditFileTool(cache).invoke(
        {"path": str(f), "old_string": "x = 1", "new_string": "x = 2"}
    )
    assert result.is_error
    assert result.error_type == "stale_file"
    # 4) 文件内容确实没被改动
    assert f.read_text() == "x = 999\n"


# 功能：验证注入 cache 但文件没被外部修改时 edit_file 正常工作
# 设计：read_file 记录后立刻 edit_file（无外部修改），断言正常替换，
#      覆盖"cache 存在但状态新鲜"的正常路径
async def test_edit_with_fresh_cache_works(tmp_path) -> None:
    from kivi_agent.core.tools.builtin.edit_file import EditFileTool
    from kivi_agent.core.tools.builtin.read_file import ReadFileTool

    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    cache = FileStateCache()
    await ReadFileTool(cache).invoke({"path": str(f)})
    result = await EditFileTool(cache).invoke(
        {"path": str(f), "old_string": "x = 1", "new_string": "x = 2"}
    )
    assert not result.is_error
    assert f.read_text() == "x = 2\n"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_edit_file_tool.py -k "stale or cache" -v`
Expected: FAIL（`EditFileTool.__init__` 不接受 `file_state_cache` 参数，TypeError）

- [ ] **Step 3: edit_file.py 追加 staleness 检查**

修改 `src/kivi_agent/core/tools/builtin/edit_file.py`：

在文件顶部 import 区域加：

```python
from kivi_agent.core.tools.file_state_cache import FileStateCache
```

`EditFileTool` 加构造器：

```python
    # 初始化：可选注入 FileStateCache；不传时不做 staleness 检查（兼容旧调用方）
    def __init__(self, file_state_cache: FileStateCache | None = None) -> None:
        super().__init__()
        self._cache = file_state_cache
```

`invoke()` 方法在 `if ".." in Path(p.path).parts: raise PermissionError(...)` 之后、读文件之前插入：

```python
        if self._cache is not None:
            stale_result = self._check_staleness(path)
            if stale_result is not None:
                return stale_result
```

**关键位置约束（再次提醒）**：在 `_atomic_write` 静态方法**下方**追加 `_check_staleness` 实例方法。完整骨架：

```python
    # 在文件中唯一匹配 old_string 并替换为 new_string，原子写回；未命中或多处命中时拒绝执行
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = EditFileParams.model_validate(params)

        if ".." in Path(p.path).parts:
            raise PermissionError(f"path traversal not allowed: {p.path}")

        path = Path(p.path)

        # 注入 cache 时检查文件是否在 read_file 之后被外部修改（避免改到错的内容）
        if self._cache is not None:
            stale_result = self._check_staleness(path)
            if stale_result is not None:
                return stale_result

        content = path.read_text(encoding="utf-8")  # raises FileNotFoundError if absent

        count = content.count(p.old_string)
        if count == 0:
            return ToolResult(
                content=f"old_string not found in {p.path}",
                is_error=True,
                error_type="runtime_error",
            )
        if count > 1:
            return ToolResult(
                content=f"old_string is not unique in {p.path}: {count} occurrences found",
                is_error=True,
                error_type="runtime_error",
            )

        new_content = content.replace(p.old_string, p.new_string, 1)
        self._atomic_write(path, new_content)

        return ToolResult(content=f"edited {p.path}")

    # 原子写入：先写同目录临时文件，再 rename 覆盖目标，避免写到一半崩溃导致文件损坏
    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    # 文件过期检查：cache 报告 is_stale 时返回错误 ToolResult，否则返回 None 放行。
    # 放在 _atomic_write 下方，方便集成时按文件行号把包 C 改动和基础闭环 Task 4 拼起来。
    def _check_staleness(self, path: Path) -> ToolResult | None:
        if self._cache is None or not self._cache.has(path):
            return None  # 没记录过或没注入 cache，视为新鲜
        if self._cache.is_stale(path):
            return ToolResult(
                content=(
                    f"file {path} has been modified since last read; "
                    "re-read it with read_file before editing"
                ),
                is_error=True,
                error_type="stale_file",
            )
        return None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_edit_file_tool.py -v`
Expected: 全部通过（原有 4 个 + 新增 3 个 = 7 passed）

- [ ] **Step 5: runner 注入共享 FileStateCache**

修改 `src/kivi_agent/core/runner.py`：

顶部 import 加：

```python
from kivi_agent.core.tools.file_state_cache import FileStateCache
```

`AgentRunner.__init__` 加参数并初始化 cache：

```python
        self._file_state_cache = FileStateCache()
```

`_build_registry` 把 cache 注入 `ReadFileTool` 和 `EditFileTool`。在现有 `for t in [ReadFileTool(), BashTool(), WriteFileTool(), ListDirTool()]:` 那个块里改 ReadFileTool 和 EditFileTool（EditFileTool 在后续也需要加进去）：

```python
        # file_state_cache（agent: package-c）
        # ReadFileTool 和 EditFileTool 共享同一份 cache，
        # 读时记录、编辑前检查"读后改"过期
        registry = ToolRegistry()
        for t in [ReadFileTool(self._file_state_cache), BashTool(), WriteFileTool(), ListDirTool()]:
            if _ok(t.name):
                registry.register(t)
        for t in [
            TaskCreateTool(task_manager),
            TaskUpdateTool(task_manager),
            TaskListTool(task_manager),
            TaskGetTool(task_manager),
        ]:
            if _ok(t.name):
                registry.register(t)
        # edit_file（agent: package-c 增强 staleness）
        if _ok("edit_file"):
            registry.register(EditFileTool(self._file_state_cache))
```

并在 `from kivi_agent.core.tools.builtin import (...)` 块里加 `EditFileTool`：

```python
from kivi_agent.core.tools.builtin import (
    AskUserTool,
    BashTool,
    EditFileTool,
    ListDirTool,
    NoteSaveTool,
    ReadFileTool,
    TaskCreateTool,
    TaskGetTool,
    TaskListTool,
    TaskUpdateTool,
    WriteFileTool,
)
```

**注意**：本步骤假设 `EditFileTool` 已经在基础闭环计划（`2026-07-20-kivi-agent-minimal-loop.md` Task 4）里落地。如果基础闭环 Task 4 还没合并，本步骤的 EditFileTool 导入会失败——届时把这一行注释掉、`if _ok("edit_file")` 整段用 `# fmt: off` 跳过，等基础闭环合并后回来补。

- [ ] **Step 6: 全量回归**

Run: `uv run pytest tests/unit -v`
Expected: 全部通过

Run: `uv run ruff check src tests`
Run: `uv run mypy src`
Expected: 全部通过

- [ ] **Step 7: 提交**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-package-c-plan"
git add src/kivi_agent/core/tools/builtin/edit_file.py \
        src/kivi_agent/core/runner.py \
        tests/unit/test_edit_file_tool.py
git commit -m "feat: edit_file 接入 FileStateCache staleness 检查（防 read 后外部改）"
```

---

### Task C6: FileHistory 快照机制

**Files:**
- Create: `src/kivi_agent/core/filehistory/history.py`
- Create: `src/kivi_agent/core/filehistory/__init__.py`
- Test: `tests/unit/test_file_history.py`

**Interfaces:**
- Produces: `@dataclass class FileSnapshot`（`version: str, path: str, ts: str, size: int, content: bytes`）、`class FileHistory`（`__init__(root: Path)`、`snapshot(path: Path) -> FileSnapshot`、`list_versions(path: Path) -> list[FileSnapshot]`、`get_version(path: Path, version: str) -> FileSnapshot`、`get_path(path: Path, version: str) -> Path`）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_file_history.py
from __future__ import annotations

import time
from pathlib import Path

from kivi_agent.core.filehistory.history import FileHistory, FileSnapshot


# 功能：验证 snapshot 后 list_versions 能看到一条记录且内容一致
# 设计：写文件→snapshot→list，覆盖"快照写入+读取"完整路径
def test_snapshot_and_list(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("hello")
    snap = history.snapshot(f)
    assert snap.content == b"hello"
    versions = history.list_versions(f)
    assert len(versions) == 1
    assert versions[0].version == snap.version
    assert versions[0].content == b"hello"


# 功能：验证多次 snapshot 按时间顺序保留所有版本（追加式，不覆盖）
# 设计：连续 snapshot 3 次（内容不同），断言 list 返回 3 条且时间戳单调递增
def test_multiple_snapshots_preserved_in_order(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("v1")
    s1 = history.snapshot(f)
    time.sleep(0.01)  # 确保 ts 不同
    f.write_text("v2")
    s2 = history.snapshot(f)
    time.sleep(0.01)
    f.write_text("v3")
    s3 = history.snapshot(f)
    versions = history.list_versions(f)
    assert [v.version for v in versions] == [s1.version, s2.version, s3.version]
    assert [v.content for v in versions] == [b"v1", b"v2", b"v3"]


# 功能：验证 get_version 能按 version id 取回对应快照
# 设计：写文件 v1→snapshot→改写为 v2→snapshot，然后分别 get 两条，
#      断言 content 与 snapshot 时一致
def test_get_version_returns_specific_snapshot(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("v1")
    s1 = history.snapshot(f)
    f.write_text("v2")
    s2 = history.snapshot(f)

    v1_loaded = history.get_version(f, s1.version)
    v2_loaded = history.get_version(f, s2.version)
    assert v1_loaded.content == b"v1"
    assert v2_loaded.content == b"v2"


# 功能：验证不存在的 version 抛 FileNotFoundError
# 设计：调用 get_version 传一个编造的 version id，断言异常类型便于上层工具返回明确错误
def test_get_unknown_version_raises(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    f = tmp_path / "x.txt"
    with __import__("pytest").raises(FileNotFoundError):
        history.get_version(f, "v9999")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_file_history.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'kivi_agent.core.filehistory'`）

- [ ] **Step 3: 实现 FileHistory**

```python
# src/kivi_agent/core/filehistory/__init__.py
from kivi_agent.core.filehistory.history import FileHistory, FileSnapshot

__all__ = ["FileHistory", "FileSnapshot"]
```

```python
# src/kivi_agent/core/filehistory/history.py
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class FileSnapshot:
    version: str  # 时间戳形式的唯一 id，如 "20260721_120304_123456"
    path: str  # 原始文件相对路径
    ts: str  # ISO 8601
    size: int
    content: bytes


# 文件历史快照：每次调用 snapshot() 把当前内容复制到 root 目录下
# <sanitized_path>/<version>.bak，按时间戳排序；get_version 按 version id 取回原内容。
# 路径存储用相对路径做子目录（避免文件名冲突），特殊字符替换为下划线。
class FileHistory:
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()
        self._root.mkdir(parents=True, exist_ok=True)

    # 把原始路径净化成可作为目录名的字符串（"src/a.py" → "src_a.py"）
    @staticmethod
    def _sanitize(path: Path) -> str:
        s = str(path).replace("\\", "/")
        s = re.sub(r"[^A-Za-z0-9_./-]", "_", s)
        s = s.replace("/", "_")
        return s or "root"

    # 当前时间戳作为 version id（微秒精度保证同秒内也不冲突）
    @staticmethod
    def _now_version() -> tuple[str, str]:
        now = datetime.now(UTC)
        version = now.strftime("%Y%m%d_%H%M%S_%f")
        iso = now.isoformat()
        return version, iso

    # 快照目录：<root>/<sanitized_path>/
    def _dir(self, path: Path) -> Path:
        d = self._root / self._sanitize(path)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # 快照文件路径：<root>/<sanitized_path>/<version>.bak
    def _file(self, path: Path, version: str) -> Path:
        return self._dir(path) / f"{version}.bak"

    # 把 path 当前内容写到 root 下的一个 .bak 文件，返回 FileSnapshot
    def snapshot(self, path: Path) -> FileSnapshot:
        version, iso = self._now_version()
        content = path.read_bytes()
        target = self._file(path, version)
        target.write_bytes(content)
        return FileSnapshot(
            version=version,
            path=str(path),
            ts=iso,
            size=len(content),
            content=content,
        )

    # 列出 path 这个文件的所有快照版本，按 version id（时间戳）升序
    def list_versions(self, path: Path) -> list[FileSnapshot]:
        d = self._dir(path)
        results: list[FileSnapshot] = []
        for bak in sorted(d.glob("*.bak")):
            version = bak.stem
            content = bak.read_bytes()
            results.append(
                FileSnapshot(
                    version=version,
                    path=str(path),
                    ts="",  # 列出时不再回查 ISO 字符串
                    size=len(content),
                    content=content,
                )
            )
        return results

    # 按 version id 取回指定快照；不存在抛 FileNotFoundError
    def get_version(self, path: Path, version: str) -> FileSnapshot:
        bak = self._file(path, version)
        if not bak.exists():
            raise FileNotFoundError(f"no snapshot version '{version}' for {path}")
        content = bak.read_bytes()
        return FileSnapshot(
            version=version,
            path=str(path),
            ts="",
            size=len(content),
            content=content,
        )

    # 返回快照文件的磁盘路径（rewind 时直接用，避免在内存里多读一遍）
    def get_path(self, path: Path, version: str) -> Path:
        return self._file(path, version)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_file_history.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: lint + 类型检查**

Run: `uv run ruff check src/kivi_agent/core/filehistory tests/unit/test_file_history.py`
Run: `uv run mypy src/kivi_agent/core/filehistory`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-package-c-plan"
git add src/kivi_agent/core/filehistory/ tests/unit/test_file_history.py
git commit -m "feat: 新增 FileHistory 快照机制（stash 风格 .bak 文件）"
```

---

### Task C7: FileHistory.rewind + rewind_file 工具

**Files:**
- Modify: `src/kivi_agent/core/filehistory/history.py`（加 `rewind(path, version) -> None`）
- Create: `src/kivi_agent/core/tools/builtin/rewind_file.py`
- Modify: `src/kivi_agent/core/runner.py`（注入 `FileHistory`、注册 `rewind_file` 工具）
- Modify: `src/kivi_agent/core/permissions/policy.py::DEFAULT_POLICIES`（登记 `rewind_file` 策略）
- Test: `tests/unit/test_rewind_file_tool.py`

**Interfaces:**
- Produces: `FileHistory.rewind(path: Path, version: str) -> None`（从指定 version 还原文件内容；用既有的 `_atomic_write` 模式确保原子）；`class RewindFileTool(BaseTool)`，`name = "rewind_file"`，构造参数 `(file_history: FileHistory)`，`params: {path: str, version: str}`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_rewind_file_tool.py
from __future__ import annotations

from pathlib import Path

import pytest

from kivi_agent.core.filehistory.history import FileHistory
from kivi_agent.core.tools.builtin.rewind_file import RewindFileTool


# 功能：验证 rewind 把文件内容还原到指定 version 的快照
# 设计：写 v1→snapshot→改写为 v2→snapshot→改写为 v3，调 rewind(v1)，
#      断言文件内容回到 v1；不依赖工具直接测 FileHistory.rewind 也行，但用工具覆盖端到端
async def test_rewind_restores_to_target_version(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("v1")
    s1 = history.snapshot(f)
    f.write_text("v2")
    history.snapshot(f)
    f.write_text("v3 (current, broken)")

    tool = RewindFileTool(history)
    result = await tool.invoke({"path": str(f), "version": s1.version})
    assert not result.is_error
    assert f.read_text() == "v1"


# 功能：验证 path 不在 history 里时返回明确错误
# 设计：snapshot 一个文件、创建另一个未 snapshot 的文件、rewind 它，断言 is_error=True
#      覆盖"目标文件没有历史记录"这条边界（不会创建空快照）
async def test_rewind_unknown_path_returns_error(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("hello")
    # 不 snapshot，直接 rewind → 应报错而不是悄悄创建空快照
    tool = RewindFileTool(history)
    result = await tool.invoke({"path": str(f), "version": "v1"})
    assert result.is_error
    assert "no history" in result.content.lower() or "not found" in result.content.lower()


# 功能：验证 version 不存在时返回明确错误
# 设计：snapshot 一次但 rewind 一个不存在的 version，断言 is_error=True
async def test_rewind_unknown_version_returns_error(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("v1")
    history.snapshot(f)
    tool = RewindFileTool(history)
    result = await tool.invoke({"path": str(f), "version": "v9999"})
    assert result.is_error
    assert result.error_type == "runtime_error"


# 功能：验证 path 中包含 .. 时抛 PermissionError
# 设计：与既有 edit_file / read_file 保持一致的安全边界
async def test_rewind_path_traversal_raises(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    tool = RewindFileTool(history)
    with pytest.raises(PermissionError):
        await tool.invoke({"path": "../etc/passwd", "version": "v1"})


# 功能：验证 rewind 后该文件原本的当前内容也作为一个新快照被自动保存
# 设计：先做 s1（v1）、改写为 v2、rewind 到 s1，断言多出一条快照（rewind 前自动备份）
#      这样"连续 rewind 不会丢版本"，回滚本身也可回滚
async def test_rewind_creates_snapshot_of_pre_rewind_state(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("v1")
    s1 = history.snapshot(f)
    f.write_text("v2 broken")
    tool = RewindFileTool(history, snapshot_before_rewind=True)
    result = await tool.invoke({"path": str(f), "version": s1.version})
    assert not result.is_error
    versions = history.list_versions(f)
    # 至少 2 个版本：s1（v1）和 rewind 前自动存的 v2 快照
    assert len(versions) >= 2
    assert versions[-1].content == b"v2 broken"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_rewind_file_tool.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: FileHistory.rewind 加方法**

在 `src/kivi_agent/core/filehistory/history.py` 末尾追加（`get_path` 后面）：

```python
    # 把文件内容还原到 version 指定的快照；文件不存在时抛 FileNotFoundError，
    # version 不存在时抛 FileNotFoundError；用原子写入避免写到一半损坏
    def rewind(self, path: Path, version: str) -> None:
        import os
        import tempfile

        snap = self.get_version(path, version)  # raises FileNotFoundError if missing
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(snap.content)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
```

并在顶部 import 加 `import os` 和 `import tempfile`（如果还没加；也可以函数内 import，跟上面代码一致）。

- [ ] **Step 4: 实现 rewind_file 工具**

```python
# src/kivi_agent/core/tools/builtin/rewind_file.py
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.filehistory.history import FileHistory
from kivi_agent.core.tools.base import BaseTool, ToolResult


class RewindFileParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str
    version: str


class RewindFileTool(BaseTool):
    params_model = RewindFileParams
    name = "rewind_file"
    description = (
        "Restore a file to a previous snapshot version created by edit_file or write_file. "
        "Use `list_file_versions` first to see available versions, then pass the chosen "
        "version id. By default a snapshot of the current (about-to-be-overwritten) "
        "content is taken first, so the rewind itself is reversible."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to the file (relative to cwd)."},
            "version": {"type": "string", "description": "Version id returned by list_file_versions."},
        },
        "required": ["path", "version"],
    }

    # 初始化：注入 FileHistory；snapshot_before_rewind 控制是否在还原前自动备份当前内容
    def __init__(self, file_history: FileHistory, *, snapshot_before_rewind: bool = True) -> None:
        super().__init__()
        self._history = file_history
        self._snapshot_before = snapshot_before_rewind

    # 还原文件到指定 version；目标文件无历史时返回明确错误而不是抛 FileNotFoundError
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = RewindFileParams.model_validate(params)

        if ".." in Path(p.path).parts:
            raise PermissionError(f"path traversal not allowed: {p.path}")

        path = Path(p.path)
        # 目标文件没有过任何快照：明确告知，避免悄悄创建空快照
        if not self._history.list_versions(path):
            return ToolResult(
                content=f"no history for {p.path}; cannot rewind a file that has never been snapshotted",
                is_error=True,
                error_type="runtime_error",
            )

        # 自动备份当前内容（rewind 本身也可回滚）
        if self._snapshot_before:
            self._history.snapshot(path)

        try:
            self._history.rewind(path, p.version)
        except FileNotFoundError as exc:
            return ToolResult(content=str(exc), is_error=True, error_type="runtime_error")

        return ToolResult(content=f"rewound {p.path} to version {p.version}")
```

- [ ] **Step 5: runner 注入 FileHistory + 注册 rewind_file**

修改 `src/kivi_agent/core/runner.py`：

顶部 import 加：

```python
from kivi_agent.core.filehistory.history import FileHistory
```

`AgentRunner.__init__` 加字段（与 `_file_state_cache` 一起）：

```python
        # file_history（agent: package-c）—— 存放在 <project>/.kivi/file-history/
        self._file_history = FileHistory(Path.cwd() / ".kivi" / "file-history")
```

`_build_registry` 末尾追加注册段，**带锚点注释**：

```python
        # rewind_file（agent: package-c）
        if _ok("rewind_file"):
            registry.register(RewindFileTool(self._file_history))
```

并在 `from kivi_agent.core.tools.builtin import (...)` 块里加 `RewindFileTool`：

```python
from kivi_agent.core.tools.builtin import (
    AskUserTool,
    BashTool,
    EditFileTool,
    ListDirTool,
    NoteSaveTool,
    ReadFileTool,
    RewindFileTool,
    TaskCreateTool,
    TaskGetTool,
    TaskListTool,
    TaskUpdateTool,
    WriteFileTool,
)
```

**注意**：`FileHistory` 路径硬编码 `Path.cwd() / ".kivi" / "file-history"` 在 runner 启动时一次性求值；如果你后续要让 `FileHistory` 也支持 per-session 目录（类似 `note_save` 的 `store, session.id, run_id` 注入），单独在另一个 task 改。本任务只做"单实例 cwd 下 `.kivi/file-history/`"。

- [ ] **Step 6: policy.py 登记 rewind_file 策略**

在 `DEFAULT_POLICIES` 加：

```python
    # rewind_file（agent: package-c）
    "rewind_file": ToolPolicy(default=PermissionDecision.ASK),
```

并在 `_PREVIEW_KEY` 加：

```python
    "rewind_file": "path",
```

- [ ] **Step 7: 全量回归**

Run: `uv run pytest tests/unit/test_rewind_file_tool.py tests/unit/test_file_history.py -v`
Expected: 全部通过

Run: `uv run pytest tests/unit -v`
Expected: 全部通过

Run: `uv run ruff check src tests`
Run: `uv run mypy src`
Expected: 全部通过

- [ ] **Step 8: 提交**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-package-c-plan"
git add src/kivi_agent/core/filehistory/history.py \
        src/kivi_agent/core/tools/builtin/rewind_file.py \
        src/kivi_agent/core/runner.py \
        src/kivi_agent/core/permissions/policy.py \
        tests/unit/test_rewind_file_tool.py
git commit -m "feat: FileHistory.rewind + rewind_file 工具（带 snapshot_before_rewind 自动备份）"
```

---

### Task C8: 端到端验收 + plan 收尾

**Files:**
- 无代码变更；仅跑全量验证 + 在本 plan 末尾追加自检

- [ ] **Step 1: 全量测试 + lint + 类型检查**

Run: `uv run pytest tests/unit -v`
Expected: 全部通过（应有 ≥ 20 个新增测试用例覆盖 ask_user / FileStateCache / FileHistory / rewind_file）

Run: `uv run ruff check src tests`
Run: `uv run mypy src`
Expected: 全部通过

- [ ] **Step 2: 跨包锚点核查**

Run: `grep -n "agent: package-c" src/kivi_agent/core/runner.py src/kivi_agent/core/permissions/policy.py`
Expected: 至少命中以下行：
- `runner.py`：`# ask_user（agent: package-c）`、`# rewind_file（agent: package-c）`、`# file_state_cache（agent: package-c）`、`# edit_file（agent: package-c 增强 staleness）`
- `policy.py`：`# ask_user（agent: package-c）`、`# rewind_file（agent: package-c）`

- [ ] **Step 3: edit_file 集成位置确认**

Run: `grep -n "_atomic_write\|_check_staleness" src/kivi_agent/core/tools/builtin/edit_file.py`
Expected: `_atomic_write`（基础闭环 Task 4 加的）在第 N 行，`_check_staleness`（本包 C5 加的）紧接其后，**行号 > N**，确认 C5 的"追加在 _atomic_write 下方"约束被遵守

- [ ] **Step 4: 协议文档同步**

如果有修改 `core/bus/events.py`（C3 加了 `AskUserRequestedEvent`），跑：

Run: `uv run python scripts/gen_protocol_doc.py`
Expected: `WIRE_PROTOCOL.md` 重新生成（如果脚本存在）；如果不存在，跳过本步

- [ ] **Step 5: 最终提交（如有遗漏）**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-package-c-plan"
git status
# 如果有未提交的修改（例如 gen_protocol_doc 改了 WIRE_PROTOCOL.md）：
git add -A
git commit -m "chore: 同步协议文档（ask_user.requested 事件已加入 Event 联合）"
```

如果 `git status` 干净，跳过本步。

---

## Self-Review Notes

- **覆盖范围**：C1-C3 覆盖 M13（`ask_user` 工具 + QuestionStore + TUI 弹窗 + runner/policy 接入 + bus 事件）；C4-C5 覆盖 M15（FileStateCache + read_file 记录 + edit_file staleness 检查）；C6-C7 覆盖 M16（FileHistory 快照 + rewind + rewind_file 工具）。
- **Future 模式复用**：`QuestionStore` 完全照搬 `PermissionManager._pending` / `_PendingRequest` 模式（asyncio.Future + 字符串 id 映射 + `respond()` 释放），没有引入新并发原语。TUI 端的 `AskUserDialog` 也照搬 `PermissionSelect` 的 Message + post_message 模式。
- **跨包协调点已显式标注**：Global Constraints 第 6 条列出了 4 个并行 agent 共享的 `_build_registry()` / `DEFAULT_POLICIES` 锚点；Task C3 / C5 / C7 在所有新增/修改处都加了 `# <tool_name>（agent: package-c）` 注释，方便第 1 波集成按注释去重。
- **edit_file 集成位置约束已遵守**：Task C5 明确要求 `_check_staleness` 放在 `_atomic_write` 静态方法**下方**，C8 Step 3 用 `grep` 自动验证行号顺序。
- **包 B 兼容性**：`EditFileTool` 和 `ReadFileTool` 现在都需要 `__init__` 接受构造参数，runner 的 `_build_registry` 注入 cache。如果包 B 的 `BaseTool.category` 改动先于本包合并，两边通过 `__init__` 注入构造参数不冲突；但如果包 B 假设 `BaseTool` 全部无参构造（**不太可能**，因为 `SpawnAgentTool`/`NoteSaveTool` 早就是有参构造），需要保留 `category: ClassVar[str] = "read"` 类属性（read_file）和 `category = "write"`（edit_file）——这两个赋值分别在 Task D1 Step 4 和包 C 各自的 Step 里都能加，不冲突。
- **类型一致性**：`AskUserTool.invoke()` 的签名与 `BaseTool` 完全一致；`QuestionStore` 没有跨模块副作用（除 bus 事件外），TUI 端通过事件订阅消费。`FileStateCache` 是单例（每 runner 一份），`FileHistory` 也是单例（每 runner 一份），两者都不需要新加构造参数到 `AgentLoop`。
- **未做（明确 YAGNI）**：没有做"mewcode 风格的 consolidation/dream 合并"——那是为多进程/多用户并发写记忆设计的，个人单机场景没有这个并发问题（与包 E 的"长期记忆"同理）。`FileHistory` 也没有做自动 GC（删除超过 N 天的旧快照），个人项目一天产生的快照量级不大（< 1000 个），如果一年后磁盘成问题再单独加一个 task。
