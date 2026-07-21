# kamaAgent 包D：权限模式 + 钩子 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 KamaClaude 加两块能力：① 权限模式（`PermissionMode`：DEFAULT/ACCEPT_EDITS/PLAN/BYPASS），在现有 `PermissionDecision(ALLOW/DENY/ASK)` 三态评估之上加一层模式覆盖；② 生命周期钩子系统，让工具调用前可拒绝、调用后可异步触发自定义逻辑，为后续包 F（团队协调策略）提供扩展点。

**Architecture:** 不改动 `PermissionManager.check_and_wait()` 的既有分层评估逻辑（deny_patterns → outside_cwd → session/persistent 缓存 → allow_patterns → tool default），而是在最前面插入一层"模式覆盖"：模式给出的决策优先于后续所有层。钩子是全新的独立包 `core/hooks/`，只在 `core/tools/invocation.py::invoke_tool()` 的固定两个点被调用（工具执行前、工具执行后），不侵入 `core/loop.py`。

**Tech Stack:** Python 3.12、pydantic v2（沿用工具/事件模型风格）、pytest + pytest-asyncio、uv。

## Global Constraints

- 遵守仓库 `CLAUDE.md`：每个函数上方一行中文注释；每个测试函数上方两行中文注释（`# 功能：`/`# 设计：`）。
- 测试命令：`uv run pytest tests/unit/test_xxx.py -v`；全量回归：`uv run pytest tests/unit -v`。
- **跨包协调点（必读）**：Task D1 给 `BaseTool` 新增 `category: ClassVar[str]` 字段。包 B（模型/工具执行增强）的并发工具批次也需要同一个字段来判断"只读工具可并发"。两个包如果都独立加这个字段，字段名和取值集合必须完全一致（`"read" | "write" | "command" | "other"`），否则第 1 波结束后的集成任务无法简单去重合并。若包 B 先落地，D1 改成"确认字段已存在，只补齐 D 用到的分类值"而不是重新定义。
- 所有新工具（`exit_plan_mode`）必须在 `core/runner.py::_build_registry()` 里按现有 `if _ok(t.name): registry.register(t)` 的模式接入（`_ok` 是 `_build_registry` 内部的白名单过滤闭包，不是全局函数），并在 `core/permissions/policy.py::DEFAULT_POLICIES` 登记默认策略。

---

### Task D1: BaseTool 加 category 字段，给现有内置工具打标

**Files:**
- Modify: `src/kama_claude/core/tools/base.py`
- Modify: `src/kama_claude/core/tools/builtin/read_file.py`、`list_dir.py`、`write_file.py`、`bash.py`、`note_save.py`、`task_create.py`、`task_get.py`、`task_list.py`、`task_update.py`
- Test: `tests/unit/test_tool_categories.py`

**Interfaces:**
- Produces: `BaseTool.category: ClassVar[str] = "other"`（取值集合 `"read" | "write" | "command" | "other"`）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_tool_categories.py
from __future__ import annotations

from kama_claude.core.tools.builtin.bash import BashTool
from kama_claude.core.tools.builtin.read_file import ReadFileTool
from kama_claude.core.tools.builtin.write_file import WriteFileTool


# 功能：验证只读类工具被标记为 category="read"
# 设计：直接读类属性而不实例化调用，因为分类是静态元数据，不依赖运行时状态
def test_read_only_tools_are_category_read() -> None:
    assert ReadFileTool.category == "read"


# 功能：验证会修改文件系统状态的工具被标记为 category="write"
# 设计：write_file 明确是写类工具，用它做代表性断言
def test_write_tools_are_category_write() -> None:
    assert WriteFileTool.category == "write"


# 功能：验证执行任意 shell 命令的工具被标记为 category="command"（语义上可读可写，单独归一类）
# 设计：bash 无法静态判断读写，归为独立的 "command" 类，供权限模式矩阵和并发判断区别对待
def test_bash_is_category_command() -> None:
    assert BashTool.category == "command"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_tool_categories.py -v`
Expected: FAIL（`AttributeError: type object 'ReadFileTool' has no attribute 'category'`）

- [ ] **Step 3: 给 BaseTool 加字段**

在 `core/tools/base.py` 的 `class BaseTool(ABC):` 里加：

```python
class BaseTool(ABC):
    name: str
    description: str
    input_schema: dict[str, object]
    params_model: ClassVar[type[BaseModel] | None] = None
    # 工具分类："read"（只读，可并发）｜"write"（改写文件状态）｜"command"（任意命令执行）｜"other"（默认）
    category: ClassVar[str] = "other"

    @abstractmethod
    async def invoke(self, params: dict[str, object]) -> ToolResult: ...
```

- [ ] **Step 4: 给现有工具打标**

在对应工具类里加一行类属性（示例，其余同理）：

```python
# core/tools/builtin/read_file.py, list_dir.py
class ReadFileTool(BaseTool):
    category = "read"
    ...

# core/tools/builtin/write_file.py, note_save.py
class WriteFileTool(BaseTool):
    category = "write"
    ...

# core/tools/builtin/bash.py
class BashTool(BaseTool):
    category = "command"
    ...

# core/tools/builtin/task_create.py, task_update.py
class TaskCreateTool(BaseTool):
    category = "write"
    ...

# core/tools/builtin/task_get.py, task_list.py
class TaskGetTool(BaseTool):
    category = "read"
    ...
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_tool_categories.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: 提交**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/KamaClaude"
git add src/kama_claude/core/tools/base.py src/kama_claude/core/tools/builtin/ tests/unit/test_tool_categories.py
git commit -m "feat: 给 BaseTool 加 category 字段并为内置工具分类"
```

---

### Task D2: PermissionMode 枚举与决策矩阵

**Files:**
- Create: `src/kama_claude/core/permissions/modes.py`
- Test: `tests/unit/test_permission_modes.py`

**Interfaces:**
- Consumes: `BaseTool.category`（Task D1）、`PermissionDecision`（`core/permissions/policy.py`，已存在）
- Produces: `class PermissionMode(StrEnum)`；`def mode_override(mode: PermissionMode, category: str) -> PermissionDecision | None`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_permission_modes.py
from __future__ import annotations

from kama_claude.core.permissions.modes import PermissionMode, mode_override
from kama_claude.core.permissions.policy import PermissionDecision


# 功能：验证 BYPASS 模式下任意分类的工具都被直接放行
# 设计：分别用 read/write/command 三种分类调用，断言全部返回 ALLOW，覆盖模式的"全放行"语义
def test_bypass_mode_allows_everything() -> None:
    for category in ("read", "write", "command"):
        assert mode_override(PermissionMode.BYPASS, category) == PermissionDecision.ALLOW


# 功能：验证 PLAN 模式下 write/command 类工具被直接拒绝，read 类工具不受模式干预
# 设计：write/command 断言 DENY（计划阶段不允许真正修改），read 断言 None（交给原有 policy 逻辑决定，通常是 ALLOW）
def test_plan_mode_blocks_write_and_command_only() -> None:
    assert mode_override(PermissionMode.PLAN, "write") == PermissionDecision.DENY
    assert mode_override(PermissionMode.PLAN, "command") == PermissionDecision.DENY
    assert mode_override(PermissionMode.PLAN, "read") is None


# 功能：验证 DEFAULT 模式完全不干预，任何分类都返回 None
# 设计：DEFAULT 是"不改变现有行为"的模式，None 表示"这一层没有意见，继续走原策略"
def test_default_mode_never_overrides() -> None:
    for category in ("read", "write", "command", "other"):
        assert mode_override(PermissionMode.DEFAULT, category) is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_permission_modes.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kama_claude/core/permissions/modes.py
from __future__ import annotations

from enum import StrEnum

from kama_claude.core.permissions.policy import PermissionDecision


class PermissionMode(StrEnum):
    DEFAULT = "default"
    ACCEPT_EDITS = "accept_edits"
    PLAN = "plan"
    BYPASS = "bypass"


# 按当前权限模式和工具分类返回强制决策；None 表示该模式对此分类不干预，交给原有分层策略决定
def mode_override(mode: PermissionMode, category: str) -> PermissionDecision | None:
    if mode == PermissionMode.BYPASS:
        return PermissionDecision.ALLOW
    if mode == PermissionMode.PLAN:
        if category in ("write", "command"):
            return PermissionDecision.DENY
        return None
    if mode == PermissionMode.ACCEPT_EDITS:
        if category == "write":
            return PermissionDecision.ALLOW
        return None
    return None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_permission_modes.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add src/kama_claude/core/permissions/modes.py tests/unit/test_permission_modes.py
git commit -m "feat: 新增 PermissionMode 权限模式与决策矩阵"
```

---

### Task D3: PermissionManager 接入权限模式

**Files:**
- Modify: `src/kama_claude/core/permissions/manager.py`
- Test: `tests/unit/test_permission_manager.py`（追加用例）

**Interfaces:**
- Consumes: `PermissionMode`/`mode_override`（Task D2）
- Produces: `PermissionManager.__init__(..., mode: PermissionMode = PermissionMode.DEFAULT)`、`PermissionManager.set_mode(mode: PermissionMode) -> None`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_permission_manager.py 追加
from kama_claude.core.permissions.modes import PermissionMode


# 功能：验证 BYPASS 模式下即使工具默认策略是 ASK，也不会挂起等待审批而是直接放行
# 设计：用默认策略为 ASK 的 bash 工具（category=command）在 BYPASS 模式下调用 check_and_wait，
#      断言立即返回 True 且 decision 明确标示来自模式覆盖，而不是掉进 Future 等待
async def test_bypass_mode_skips_approval() -> None:
    from kama_claude.core.permissions.manager import PermissionManager

    manager = PermissionManager(mode=PermissionMode.BYPASS)

    async def _never_called(payload: dict) -> None:
        raise AssertionError("should not emit permission.requested in BYPASS mode")

    allowed, decision = await manager.check_and_wait(
        tool_use_id="t1",
        tool_name="bash",
        params={"command": "echo hi"},
        session_id="s1",
        event_emitter=_never_called,
    )
    assert allowed is True
    assert decision == "mode_bypass"


# 功能：验证 PLAN 模式下 write_file 这类 write 分类工具被直接拒绝，不进入审批流程
# 设计：同样用 _never_called 断言不会发出 permission.requested 事件，确认模式覆盖发生在 ask 分支之前
async def test_plan_mode_denies_write_tool() -> None:
    from kama_claude.core.permissions.manager import PermissionManager

    manager = PermissionManager(mode=PermissionMode.PLAN)

    async def _never_called(payload: dict) -> None:
        raise AssertionError("should not emit permission.requested in PLAN mode for write tools")

    allowed, decision = await manager.check_and_wait(
        tool_use_id="t2",
        tool_name="write_file",
        params={"path": "a.txt", "content": "x"},
        session_id="s1",
        event_emitter=_never_called,
    )
    assert allowed is False
    assert decision == "mode_plan_deny"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_permission_manager.py -k "bypass_mode or plan_mode" -v`
Expected: FAIL（`TypeError: PermissionManager.__init__() got an unexpected keyword argument 'mode'`）

- [ ] **Step 3: 改造 PermissionManager**

在 `core/permissions/manager.py` 顶部加 import：

```python
from kama_claude.core.permissions.modes import PermissionMode, mode_override
from kama_claude.core.tools.registry import ToolRegistry  # 用于按工具名查 category，见下方说明
```

`__init__` 加参数并保存：

```python
    def __init__(
        self,
        policies: dict[str, ToolPolicy] | None = None,
        *,
        policy_file: Path | None = None,
        timeout_s: float = 60.0,
        mode: PermissionMode = PermissionMode.DEFAULT,
        tool_categories: dict[str, str] | None = None,
    ) -> None:
        self._policies: dict[str, ToolPolicy] = policies or dict(DEFAULT_POLICIES)
        self._pending: dict[str, _PendingRequest] = {}
        self._session_always: dict[tuple[str, str], str] = {}
        self._policy_file = policy_file
        self._persistent_always: dict[str, str] = (
            load_policy_file(policy_file) if policy_file is not None else {}
        )
        self._timeout_s = timeout_s
        self._mode = mode
        # 工具名 → category 的静态映射，由调用方（runner.py）在构造时注入，避免这里反向依赖 ToolRegistry 实例
        self._tool_categories = tool_categories or {}

    # 切换当前权限模式（供 exit_plan_mode 等工具驱动的模式切换调用）
    def set_mode(self, mode: PermissionMode) -> None:
        self._mode = mode
```

**说明**：不引入 `ToolRegistry` 反向依赖——`_tool_categories` 由 `core/runner.py` 在构造 `PermissionManager` 时，从已经建好的 `ToolRegistry` 里遍历 `{t.name: t.category for t in registry.all_tools()}` 传入（`ToolRegistry` 需要有一个 `all_tools()`/等价的遍历方法；若当前没有，用 `registry._tools.values()` 风格的现有内部属性即可，不必新增公开 API）。上面 import 里的 `ToolRegistry` 仅用于类型标注，实际不在 `manager.py` 内实例化或调用它，避免循环 import——若 mypy/ruff 提示未使用，改为 `TYPE_CHECKING` 块内导入。

在 `check_and_wait()` 方法最前面（`command = str(...)` 之后、Tier 1 之前）插入模式覆盖：

```python
        category = self._tool_categories.get(tool_name, "other")
        override = mode_override(self._mode, category)
        if override is not None:
            from kama_claude.core.permissions.policy import PermissionDecision
            if override == PermissionDecision.ALLOW:
                return True, f"mode_{self._mode.value}"
            return False, f"mode_{self._mode.value}_deny"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_permission_manager.py -v`
Expected: 全部通过（含新增 2 项）

- [ ] **Step 5: runner.py 接入 tool_categories**

在 `core/runner.py` 构造 `PermissionManager` 的地方（构造函数或 `_build_registry` 之后），补充：

```python
tool_categories = {t.name: t.category for t in registry.all_tools()}
self._permission_manager.set_mode(self._permission_manager._mode)  # no-op，占位说明——实际不需要这行
```

（若 `PermissionManager` 是在 `_build_registry()` 之前就已构造好的单例，改为在构造 `PermissionManager` 时延后传入 `tool_categories`，或提供 `PermissionManager.set_tool_categories(dict[str, str]) -> None` 方法在 registry 建好后调用一次。选择哪种取决于 `runner.py` 里两者的构造顺序，实现前先确认。）

- [ ] **Step 6: 提交**

```bash
git add src/kama_claude/core/permissions/manager.py src/kama_claude/core/runner.py tests/unit/test_permission_manager.py
git commit -m "feat: PermissionManager 接入权限模式，模式覆盖优先于原有分层策略"
```

---

### Task D4: exit_plan_mode 工具

**Files:**
- Create: `src/kama_claude/core/tools/builtin/exit_plan_mode.py`
- Test: `tests/unit/test_exit_plan_mode_tool.py`
- Modify: `src/kama_claude/core/runner.py`
- Modify: `src/kama_claude/core/permissions/policy.py`

**Interfaces:**
- Consumes: `PermissionMode`（Task D2）
- Produces: `class ExitPlanModeTool(BaseTool)`，`name = "exit_plan_mode"`

**设计说明**：和 mewcode 一致的分工——工具本身只做"当前是否处于 PLAN 模式"的校验并返回确认文本，真正的模式切换（PLAN → DEFAULT/BYPASS）由调用方（TUI 或 runner）在收到这个工具调用后驱动 `PermissionManager.set_mode()`，不在工具的 `invoke()` 里直接改全局状态——工具没有到 `PermissionManager` 实例的引用，这样设计避免了工具反向持有系统级单例。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_exit_plan_mode_tool.py
from __future__ import annotations

from kama_claude.core.tools.builtin.exit_plan_mode import ExitPlanModeTool


# 功能：验证工具调用时返回的确认文本包含提交的计划摘要
# 设计：只测试工具的纯文本输出，不测试模式切换本身（切换发生在调用方，不在这个工具里）
async def test_exit_plan_mode_returns_confirmation_with_summary() -> None:
    result = await ExitPlanModeTool().invoke({"plan_summary": "先加测试再实现"})
    assert not result.is_error
    assert "先加测试再实现" in result.content
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_exit_plan_mode_tool.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kama_claude/core/tools/builtin/exit_plan_mode.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from kama_claude.core.tools.base import BaseTool, ToolResult


class ExitPlanModeParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plan_summary: str


class ExitPlanModeTool(BaseTool):
    params_model = ExitPlanModeParams
    name = "exit_plan_mode"
    category = "other"
    description = (
        "Call this when you have finished planning in plan mode and are ready to present "
        "the plan to the user for approval before executing it. Pass a concise summary of "
        "the plan. This tool does not execute anything by itself — the caller decides "
        "whether to switch out of plan mode based on the user's response."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "plan_summary": {"type": "string", "description": "Concise summary of the plan to present."},
        },
        "required": ["plan_summary"],
    }

    # 返回计划摘要的确认文本；不直接修改权限模式，模式切换由调用方驱动
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = ExitPlanModeParams.model_validate(params)
        return ToolResult(
            content=f"Plan ready for review:\n\n{p.plan_summary}\n\nAwaiting user decision."
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_exit_plan_mode_tool.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: 注册与权限策略**

`policy.py`：`"exit_plan_mode": ToolPolicy(default=PermissionDecision.ALLOW),`（工具本身只是提示确认，不做实际操作，允许自由调用）

`runner.py`：`if _ok("exit_plan_mode"): registry.register(ExitPlanModeTool())`

- [ ] **Step 6: 提交**

```bash
git add src/kama_claude/core/tools/builtin/exit_plan_mode.py tests/unit/test_exit_plan_mode_tool.py \
        src/kama_claude/core/runner.py src/kama_claude/core/permissions/policy.py
git commit -m "feat: 新增 exit_plan_mode 工具"
```

---

### Task D5: Hooks 数据模型

**Files:**
- Create: `src/kama_claude/core/hooks/__init__.py`
- Create: `src/kama_claude/core/hooks/events.py`
- Create: `src/kama_claude/core/hooks/models.py`
- Test: `tests/unit/test_hook_models.py`

**Interfaces:**
- Produces: `class LifecycleEvent(StrEnum)`（含 `PRE_TOOL_USE`/`POST_TOOL_USE`/`SESSION_START`/`SESSION_END`）
- Produces: `@dataclass class Hook`（`id, event: LifecycleEvent, command: str, condition: str | None = None, reject: bool = False, async_exec: bool = False`）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_hook_models.py
from __future__ import annotations

from kama_claude.core.hooks.events import LifecycleEvent
from kama_claude.core.hooks.models import Hook


# 功能：验证 Hook 能用最小必填字段构造，可选字段有合理默认值
# 设计：只传 id/event/command，断言 reject 默认为 False、async_exec 默认为 False，
#      确保新增字段不会破坏最简单的钩子定义
def test_hook_minimal_construction_has_safe_defaults() -> None:
    hook = Hook(id="h1", event=LifecycleEvent.PRE_TOOL_USE, command="echo pre")
    assert hook.reject is False
    assert hook.async_exec is False
    assert hook.condition is None


# 功能：验证 LifecycleEvent 至少包含工具调用前后两个核心事件类型
# 设计：这两个类型是 Task D6 HookEngine 唯一会用到的，先在这里锁定字符串值不被后续误改
def test_lifecycle_event_has_tool_hooks() -> None:
    assert LifecycleEvent.PRE_TOOL_USE.value == "pre_tool_use"
    assert LifecycleEvent.POST_TOOL_USE.value == "post_tool_use"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_hook_models.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kama_claude/core/hooks/events.py
from __future__ import annotations

from enum import StrEnum


class LifecycleEvent(StrEnum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    TURN_START = "turn_start"
    TURN_END = "turn_end"
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    COMPACT = "compact"
```

```python
# src/kama_claude/core/hooks/models.py
from __future__ import annotations

from dataclasses import dataclass

from kama_claude.core.hooks.events import LifecycleEvent


@dataclass
class Hook:
    id: str
    event: LifecycleEvent
    command: str
    # 可选的 shell 表达式，为空字符串外的求值失败/为 false 时跳过该钩子
    condition: str | None = None
    # True 时钩子返回非零退出码会阻断对应的工具调用（仅 PRE_TOOL_USE 有意义）
    reject: bool = False
    # True 时钩子在后台异步执行，不阻塞主流程等待其完成
    async_exec: bool = False
```

```python
# src/kama_claude/core/hooks/__init__.py
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_hook_models.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add src/kama_claude/core/hooks/ tests/unit/test_hook_models.py
git commit -m "feat: 新增 Hooks 数据模型（LifecycleEvent + Hook）"
```

---

### Task D6: HookEngine — 执行引擎

**Files:**
- Create: `src/kama_claude/core/hooks/engine.py`
- Modify: `src/kama_claude/core/tools/errors.py`
- Test: `tests/unit/test_hook_engine.py`

**Interfaces:**
- Consumes: `Hook`/`LifecycleEvent`（Task D5）
- Produces: `class ToolRejectedError(Exception)`（`core/tools/errors.py`，与已有 `RateLimitedError` 同文件）、`class HookEngine`，`async def run_pre_tool_hooks(self, tool_name: str, params: dict) -> None`（拒绝时抛 `ToolRejectedError`）、`async def run_post_tool_hooks(self, tool_name: str, result_summary: str) -> None`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_hook_engine.py
from __future__ import annotations

from kama_claude.core.hooks.engine import HookEngine
from kama_claude.core.hooks.events import LifecycleEvent
from kama_claude.core.hooks.models import Hook
from kama_claude.core.tools.errors import ToolRejectedError


# 功能：验证 reject=True 的钩子命令返回非零退出码时，run_pre_tool_hooks 抛出 ToolRejectedError
# 设计：用一个必然失败的 shell 命令（exit 1）模拟"钩子否决"，断言异常类型和消息包含工具名，
#      确保调用方能据此把工具调用短路掉
async def test_pre_hook_reject_raises() -> None:
    engine = HookEngine([
        Hook(id="deny-all", event=LifecycleEvent.PRE_TOOL_USE, command="exit 1", reject=True)
    ])
    try:
        await engine.run_pre_tool_hooks("bash", {"command": "rm -rf /"})
        raise AssertionError("expected ToolRejectedError")
    except ToolRejectedError as exc:
        assert "deny-all" in str(exc)


# 功能：验证 reject=False 的钩子即使命令失败也不会阻断，只是被忽略（记日志，不抛异常）
# 设计：同样用 exit 1 但 reject=False，断言 run_pre_tool_hooks 正常返回不抛异常，
#      覆盖"钩子失败默认不影响主流程"这条设计原则
async def test_non_reject_hook_failure_is_swallowed() -> None:
    engine = HookEngine([
        Hook(id="noisy", event=LifecycleEvent.PRE_TOOL_USE, command="exit 1", reject=False)
    ])
    await engine.run_pre_tool_hooks("bash", {"command": "echo hi"})  # 不应抛异常
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_hook_engine.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 加 ToolRejectedError**

在 `core/tools/errors.py`（已存在 `RateLimitedError`）追加：

```python
class ToolRejectedError(Exception):
    # 由 HookEngine 在 reject=True 的钩子否决工具调用时抛出
    pass
```

- [ ] **Step 4: 实现 HookEngine**

```python
# src/kama_claude/core/hooks/engine.py
from __future__ import annotations

import asyncio
import json
import logging

from kama_claude.core.hooks.events import LifecycleEvent
from kama_claude.core.hooks.models import Hook
from kama_claude.core.tools.errors import ToolRejectedError

logger = logging.getLogger(__name__)
_HOOK_TIMEOUT_S = 10.0


class HookEngine:
    # 初始化钩子引擎，持有全部已配置钩子的列表
    def __init__(self, hooks: list[Hook]) -> None:
        self._hooks = hooks

    # 返回指定生命周期事件下配置的钩子，保持配置顺序
    def _hooks_for(self, event: LifecycleEvent) -> list[Hook]:
        return [h for h in self._hooks if h.event == event]

    # 以 shell 子进程执行一个钩子命令，返回退出码；超时或异常按失败处理（退出码 1）
    async def _run_command(self, command: str, payload: dict[str, object]) -> int:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            payload_bytes = json.dumps(payload).encode("utf-8")
            await asyncio.wait_for(proc.communicate(payload_bytes), timeout=_HOOK_TIMEOUT_S)
            return proc.returncode or 0
        except Exception:
            logger.exception("hook command failed: %s", command)
            return 1

    # 依次执行工具调用前的钩子；任一 reject=True 的钩子返回非零退出码则抛出 ToolRejectedError
    async def run_pre_tool_hooks(self, tool_name: str, params: dict[str, object]) -> None:
        payload = {"event": LifecycleEvent.PRE_TOOL_USE.value, "tool_name": tool_name, "params": params}
        for hook in self._hooks_for(LifecycleEvent.PRE_TOOL_USE):
            code = await self._run_command(hook.command, payload)
            if code != 0:
                if hook.reject:
                    raise ToolRejectedError(f"tool call rejected by hook '{hook.id}' (exit code {code})")
                logger.warning("non-blocking pre_tool_use hook '%s' failed (exit code %d)", hook.id, code)

    # 触发工具调用后的钩子；async_exec=True 的钩子后台执行不等待，其余顺序等待完成
    async def run_post_tool_hooks(self, tool_name: str, result_summary: str) -> None:
        payload = {"event": LifecycleEvent.POST_TOOL_USE.value, "tool_name": tool_name, "result_summary": result_summary}
        for hook in self._hooks_for(LifecycleEvent.POST_TOOL_USE):
            if hook.async_exec:
                asyncio.ensure_future(self._run_command(hook.command, payload))
            else:
                await self._run_command(hook.command, payload)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_hook_engine.py -v`
Expected: PASS（2 passed）

- [ ] **Step 6: 提交**

```bash
git add src/kama_claude/core/hooks/engine.py src/kama_claude/core/tools/errors.py tests/unit/test_hook_engine.py
git commit -m "feat: 新增 HookEngine，支持前置可拒绝钩子和后置异步钩子"
```

---

### Task D7: 接入 invoke_tool()

**Files:**
- Modify: `src/kama_claude/core/tools/invocation.py`
- Test: `tests/unit/test_invocation.py`（追加用例）

**Interfaces:**
- Consumes: `HookEngine`（Task D6）
- Produces: `invoke_tool(..., hook_engine: HookEngine | None = None)` 新增可选参数

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_invocation.py 追加
from kama_claude.core.hooks.engine import HookEngine
from kama_claude.core.hooks.events import LifecycleEvent
from kama_claude.core.hooks.models import Hook


# 功能：验证 pre_tool_use 钩子拒绝时，invoke_tool 返回 is_error=True 的 ToolResult 而不是让异常向上抛出
# 设计：invoke_tool 的既有契约是"永不抛异常，失败都体现在返回值里"，
#      这里断言钩子拒绝也遵守同一契约，error_type 标记为 "permission_denied" 与既有权限拒绝路径保持一致的语义
async def test_invoke_tool_respects_hook_rejection(monkeypatch) -> None:
    from kama_claude.core.events.bus import EventBus
    from kama_claude.core.llm.types import ToolCallBlock
    from kama_claude.core.tools.registry import ToolRegistry
    from kama_claude.core.tools.builtin.bash import BashTool
    from kama_claude.core.tools.invocation import invoke_tool

    registry = ToolRegistry()
    registry.register(BashTool())
    hook_engine = HookEngine([
        Hook(id="deny", event=LifecycleEvent.PRE_TOOL_USE, command="exit 1", reject=True)
    ])
    bus = EventBus()
    result = await invoke_tool(
        registry,
        ToolCallBlock(id="t1", name="bash", input={"command": "echo hi"}),
        bus,
        run_id="r1",
        hook_engine=hook_engine,
    )
    assert result.is_error
    assert result.error_type == "permission_denied"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_invocation.py -k hook_rejection -v`
Expected: FAIL（`TypeError: invoke_tool() got an unexpected keyword argument 'hook_engine'`）

- [ ] **Step 3: 改造 invoke_tool()**

在函数签名加参数：

```python
async def invoke_tool(
    registry: ToolRegistry,
    tool_call: ToolCallBlock,
    bus: EventBus,
    run_id: str,
    timeout: float = _DEFAULT_TIMEOUT,
    *,
    permission_manager: PermissionManager | None = None,
    session_id: str = "",
    hook_engine: "HookEngine | None" = None,
) -> ToolResult:
```

在 `ToolCallStartedEvent` 发布之后、`tool = registry.get(...)` 判断之前，插入前置钩子调用：

```python
    if hook_engine is not None:
        from kama_claude.core.tools.errors import ToolRejectedError
        try:
            await hook_engine.run_pre_tool_hooks(tool_call.name, dict(tool_call.input))
        except ToolRejectedError as exc:
            return await _fail(
                bus, run_id, tool_call,
                "permission_denied", str(exc), elapsed(),
            )
```

在成功分支 `ToolCallFinishedEvent` 发布之后、`return result` 之前，插入后置钩子调用：

```python
            else:
                await bus.publish(
                    ToolCallFinishedEvent(
                        run_id=run_id,
                        tool_use_id=tool_call.id,
                        tool_name=tool_call.name,
                        elapsed_ms=ms,
                        output=result.content,
                        ts=_now(),
                    )
                )
                if hook_engine is not None:
                    await hook_engine.run_post_tool_hooks(tool_call.name, result.content[:200])
                return result
```

顶部加 `from kama_claude.core.hooks.engine import HookEngine`（放在 `TYPE_CHECKING` 块内，因为函数签名里用字符串字面量类型标注，避免与 `core/hooks` 之间产生不必要的运行时循环 import 风险）。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_invocation.py -v`
Expected: 全部通过

- [ ] **Step 5: 全量回归**

Run: `uv run pytest tests/unit -v`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add src/kama_claude/core/tools/invocation.py tests/unit/test_invocation.py
git commit -m "feat: invoke_tool 接入 HookEngine 前置/后置钩子"
```

---

### Task D8: 配置扩展 + HookLoader + runner.py 装配

**Files:**
- Modify: `src/kama_claude/core/config.py`
- Create: `src/kama_claude/core/hooks/loader.py`
- Modify: `src/kama_claude/core/runner.py`
- Test: `tests/unit/test_hook_loader.py`

**Interfaces:**
- Produces: `HooksConfig`（`config.py` 新 dataclass）、`def load_hooks(config: HooksConfig) -> list[Hook]`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_hook_loader.py
from __future__ import annotations

from kama_claude.core.config import HooksConfig, HookEntry
from kama_claude.core.hooks.events import LifecycleEvent
from kama_claude.core.hooks.loader import load_hooks


# 功能：验证 HooksConfig 里的条目能正确转换成 Hook 对象列表
# 设计：构造一个含单条 hook 配置的 HooksConfig，断言转换后的字段一一对应，
#      覆盖"配置层 → 领域对象"这层薄转换的正确性
def test_load_hooks_converts_config_entries() -> None:
    config = HooksConfig(entries=[
        HookEntry(id="fmt", event="post_tool_use", command="ruff format", reject=False, async_exec=True)
    ])
    hooks = load_hooks(config)
    assert len(hooks) == 1
    assert hooks[0].id == "fmt"
    assert hooks[0].event == LifecycleEvent.POST_TOOL_USE
    assert hooks[0].async_exec is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_hook_loader.py -v`
Expected: FAIL（`ImportError: cannot import name 'HooksConfig'`）

- [ ] **Step 3: config.py 加配置**

```python
@dataclass
class HookEntry:
    id: str
    event: str
    command: str
    condition: str | None = None
    reject: bool = False
    async_exec: bool = False


@dataclass
class HooksConfig:
    entries: list[HookEntry] = field(default_factory=list)
```

在 `KamaConfig` dataclass 里加一行：`hooks: HooksConfig = field(default_factory=HooksConfig)`（TOML 解析暂不接入 `_apply_toml`，本任务范围只做代码可配置，TOML `[[hooks]]` 数组表解析留给后续需要时再加，避免为一个当前无人使用的配置面再扩一层 unknown-key 校验代码，YAGNI）。

- [ ] **Step 4: 实现 loader**

```python
# src/kama_claude/core/hooks/loader.py
from __future__ import annotations

from kama_claude.core.config import HooksConfig
from kama_claude.core.hooks.events import LifecycleEvent
from kama_claude.core.hooks.models import Hook


# 将配置层的 HooksConfig 转换成领域对象 Hook 列表
def load_hooks(config: HooksConfig) -> list[Hook]:
    return [
        Hook(
            id=entry.id,
            event=LifecycleEvent(entry.event),
            command=entry.command,
            condition=entry.condition,
            reject=entry.reject,
            async_exec=entry.async_exec,
        )
        for entry in config.entries
    ]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_hook_loader.py -v`
Expected: PASS（1 passed）

- [ ] **Step 6: runner.py 装配**

在 `AgentRunner` 构造处（初始化 `self._permission_manager` 附近）加：

```python
from kama_claude.core.hooks.engine import HookEngine
from kama_claude.core.hooks.loader import load_hooks
# ...
self._hook_engine = HookEngine(load_hooks(self._config.hooks))
```

并在调用 `invoke_tool(...)` 的地方（`core/agents` 或调用方内部，与 `permission_manager=` 同一处）补上 `hook_engine=self._hook_engine`。

- [ ] **Step 7: 全量回归**

Run: `uv run pytest tests/unit -v`
Run: `uv run ruff check src tests`
Run: `uv run mypy src`
Expected: 全部通过

- [ ] **Step 8: 提交**

```bash
git add src/kama_claude/core/config.py src/kama_claude/core/hooks/loader.py \
        src/kama_claude/core/runner.py tests/unit/test_hook_loader.py
git commit -m "feat: HooksConfig 配置 + HookLoader + runner 装配 HookEngine"
```

---

## Self-Review Notes

- **覆盖范围**：D1-D4 覆盖 M14（计划模式）+ M19（权限模式）+ M20（沿用现有 TUI 组件，未新增文件）；D5-D8 覆盖 M21（生命周期钩子）+ M22（钩子拒绝错误分类，`ToolRejectedError` 归入既有 `permission_denied` error_type，复用而非新增分类）。
- **跨包耦合已在 Global Constraints 显式标注**：Task D1 的 `category` 字段是包 B 并发工具批次判断的前置依赖，两包并行执行时需要对齐字段名和取值。
- **类型一致性**：`PermissionManager.check_and_wait()` 的返回值类型 `tuple[bool, str]` 全程未变；`invoke_tool()` 新增的 `hook_engine` 参数是可选关键字参数，不破坏任何现有调用方（`permission_manager=None` 时函数保持原行为，`hook_engine=None` 同理）。
