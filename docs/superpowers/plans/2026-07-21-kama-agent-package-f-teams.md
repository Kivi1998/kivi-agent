# kamaAgent 包F：多 Agent 团队协作 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 kivi-agent 已有的单层 Subagent 机制（`SpawnAgentTool` + `BackgroundTaskRegistry`，深度上限 2）基础上，加一层"团队"概念：多个命名成员、成员间可寻址通信（mailbox）、协调者角色的工具白名单约束、团队整体状态查询、可选的子 Agent 工作树隔离。

**Architecture:** 不重写 Subagent 机制。先把 `SpawnAgentTool.invoke()` 里"创建并注册后台子 agent"这段逻辑抽成一个独立函数 `spawn_background_subagent()`，`SpawnAgentTool` 和新的 `TeamManager` 都调用这同一个函数——避免团队功能重新实现一遍 spawn 逻辑。团队本身是"多个通过这个函数创建的后台 subagent + 一层元数据（名字/角色/mailbox）"，不是全新的执行模型。协调者"只调度不编码"的约束复用已有的 `AgentProfile.allowed_tools` 白名单机制（不引入包 D 的 Hooks，见 Global Constraints）。

**Tech Stack:** Python 3.12、pydantic v2、pytest + pytest-asyncio、uv、Kama 现有 `AgentProfileLoader`/`BackgroundTaskRegistry`/`EventBus`。

## Global Constraints

- 遵守仓库 `CLAUDE.md`：每个函数上方一行中文注释；每个测试函数上方两行中文注释（`# 功能：`/`# 设计：`）。
- 测试命令：`uv run pytest tests/unit/test_xxx.py -v`；全量回归：`uv run pytest tests/unit -v`。
- **不做 mewcode 的 `spawn_tmux`/`spawn_iterm2` 后端**——那两个需要用户本机装 tmux/iTerm2，个人闭环没必要，只做 `asyncio.create_task` 同进程协程这一种（Kama 现有 `SpawnAgentTool` 的后台模式本来就是这个机制，直接复用）。
- **协调者约束走 `AgentProfile.allowed_tools` 白名单，不引入包 D 的 Hooks**——白名单机制已经存在且经过验证（`_build_child_registry` 里 `_allowed(name)` 已经在用），没必要为同一个目的叠两层机制，YAGNI。
- Mailbox 用文件系统实现（不是内存队列）：即使当前只支持同进程 `asyncio.create_task` 后端，文件系统 mailbox 依然有价值——team 状态需要跨 `kivi-core` 进程重启后可查（daemon 重启后台任务会丢，但已发送未消费的消息不应该跟着丢）。
- 新工具（`team_create`/`team_message`/`team_status`）必须在 `core/runner.py::_build_registry()` 里注册，并在 `core/permissions/policy.py::DEFAULT_POLICIES` 登记策略。

---

### Task F1: Team / TeammateInfo 数据模型

**Files:**
- Create: `src/kivi_agent/core/teams/__init__.py`
- Create: `src/kivi_agent/core/teams/models.py`
- Test: `tests/unit/test_team_models.py`

**Interfaces:**
- Produces: `@dataclass class TeammateInfo`（`name, role, run_id, status`）、`@dataclass class AgentTeam`（`id, goal, members`）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_team_models.py
from __future__ import annotations

from kivi_agent.core.teams.models import AgentTeam, TeammateInfo


# 功能：验证 TeammateInfo 用最小字段构造时 status 默认是 "pending"
# 设计：团队刚创建、后台任务还没跑完时的默认状态，供后续状态查询工具做初始展示
def test_teammate_info_defaults_to_pending() -> None:
    member = TeammateInfo(name="planner", role="planner", run_id="run-1")
    assert member.status == "pending"


# 功能：验证 AgentTeam 能持有多个成员并按名字查找
# 设计：team_status/team_message 工具都需要按名字定位到具体成员，覆盖这个查找路径
def test_agent_team_find_member_by_name() -> None:
    team = AgentTeam(id="team-1", goal="重构登录模块", members=[
        TeammateInfo(name="planner", role="planner", run_id="run-1"),
        TeammateInfo(name="executor", role="executor", run_id="run-2"),
    ])
    found = team.find_member("executor")
    assert found is not None
    assert found.run_id == "run-2"
    assert team.find_member("nonexistent") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_team_models.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/teams/models.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TeammateInfo:
    name: str
    role: str
    run_id: str
    status: str = "pending"  # "pending" | "running" | "success" | "failed"


@dataclass
class AgentTeam:
    id: str
    goal: str
    members: list[TeammateInfo] = field(default_factory=list)

    # 按名字查找团队成员；不存在返回 None
    def find_member(self, name: str) -> TeammateInfo | None:
        for m in self.members:
            if m.name == name:
                return m
        return None
```

```python
# src/kivi_agent/core/teams/__init__.py
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_team_models.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-agent"
git add src/kivi_agent/core/teams/ tests/unit/test_team_models.py
git commit -m "feat: 新增 Team/TeammateInfo 数据模型"
```

---

### Task F2: Mailbox — 文件系统跨进程邮箱

**Files:**
- Create: `src/kivi_agent/core/teams/mailbox.py`
- Test: `tests/unit/test_mailbox.py`

**Interfaces:**
- Produces: `def write_message(mailbox_root: Path, recipient: str, sender: str, content: str) -> None`、`def consume_messages(mailbox_root: Path, recipient: str) -> list[dict[str, str]]`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_mailbox.py
from __future__ import annotations

from pathlib import Path

from kivi_agent.core.teams.mailbox import consume_messages, write_message


# 功能：验证写入一条消息后，收件人能通过 consume_messages 读到，且读取后消息被清空
# 设计："consume"语义是取走即删除，覆盖"读两次第二次应该是空"这个核心行为
def test_write_then_consume_drains_mailbox(tmp_path: Path) -> None:
    write_message(tmp_path, recipient="executor", sender="planner", content="先看 auth.py")
    messages = consume_messages(tmp_path, "executor")
    assert len(messages) == 1
    assert messages[0]["sender"] == "planner"
    assert messages[0]["content"] == "先看 auth.py"

    second_read = consume_messages(tmp_path, "executor")
    assert second_read == []


# 功能：验证同一收件人收到的多条消息按写入顺序全部返回
# 设计：team_message 可能被连续调用多次，消费时不能丢消息也不能乱序
def test_multiple_messages_preserved_in_order(tmp_path: Path) -> None:
    write_message(tmp_path, recipient="executor", sender="planner", content="first")
    write_message(tmp_path, recipient="executor", sender="planner", content="second")
    messages = consume_messages(tmp_path, "executor")
    assert [m["content"] for m in messages] == ["first", "second"]


# 功能：验证给不同收件人写的消息互不干扰
# 设计：mailbox 按收件人隔离，覆盖"executor 消费不会拿到 reviewer 的信"这个边界
def test_messages_isolated_per_recipient(tmp_path: Path) -> None:
    write_message(tmp_path, recipient="executor", sender="planner", content="for executor")
    write_message(tmp_path, recipient="reviewer", sender="planner", content="for reviewer")
    assert [m["content"] for m in consume_messages(tmp_path, "executor")] == ["for executor"]
    assert [m["content"] for m in consume_messages(tmp_path, "reviewer")] == ["for reviewer"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_mailbox.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/teams/mailbox.py
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


# 把一条消息以独立文件写入收件人目录；用 O_CREAT|O_EXCL 保证并发写入不互相覆盖
def write_message(mailbox_root: Path, recipient: str, sender: str, content: str) -> None:
    recipient_dir = mailbox_root / "mailbox" / recipient
    recipient_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"sender": sender, "content": content, "ts": _now()}, ensure_ascii=False)
    # 文件名含单调递增的纳秒时间戳，保证 sorted() 遍历顺序等价于写入顺序
    filename = f"{time.time_ns()}_{uuid.uuid4().hex[:8]}.json"
    path = recipient_dir / filename
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)


# 读取并清空指定收件人的所有待处理消息，按写入顺序返回
def consume_messages(mailbox_root: Path, recipient: str) -> list[dict[str, str]]:
    recipient_dir = mailbox_root / "mailbox" / recipient
    if not recipient_dir.exists():
        return []
    messages: list[dict[str, str]] = []
    for path in sorted(recipient_dir.glob("*.json")):
        try:
            messages.append(json.loads(path.read_text(encoding="utf-8")))
        finally:
            path.unlink(missing_ok=True)
    return messages
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_mailbox.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add src/kivi_agent/core/teams/mailbox.py tests/unit/test_mailbox.py
git commit -m "feat: 新增文件系统 Mailbox，支持团队成员间点对点消息"
```

---

### Task F3: 提取 spawn_background_subagent 共享函数

**Files:**
- Modify: `src/kivi_agent/core/subagent/tool.py`
- Test: `tests/unit/test_subagent_tool.py`（追加用例，若文件不存在则新建）

**Interfaces:**
- Produces: `async def spawn_background_subagent(*, provider, parent_bus, parent_run_id, permission_manager, max_steps, task_registry, runs_dir, session_id, depth, description, prompt, subagent_type="") -> str`（返回 `child_run_id`）

**设计说明**：这是纯重构任务——把 `SpawnAgentTool.invoke()` 里 `p.run_in_background=True` 分支的逻辑原样搬到一个模块级函数里，`SpawnAgentTool.invoke()` 改为调用它。行为不变，只是让 Task F4 的 `TeamCreateTool` 能复用同一段逻辑而不必解析 `SpawnAgentTool` 返回的自然语言文本拿 `run_id`。

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_subagent_tool.py（如已存在则追加，以下假设新建）
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.subagent.registry import BackgroundTaskRegistry
from kivi_agent.core.subagent.tool import spawn_background_subagent


# 功能：验证 spawn_background_subagent 直接返回 run_id 字符串，而不是包一层 ToolResult 文本
# 设计：这是 Task F4 TeamManager 复用这个函数的前提——需要能直接拿到 run_id 编程使用，
#      不应该依赖解析"...run_id=xxx..."这种自然语言格式
async def test_spawn_background_subagent_returns_run_id(tmp_path: Path) -> None:
    fake_provider = AsyncMock()
    fake_provider.chat.return_value.text = "done"
    fake_provider.chat.return_value.stop_reason = "end_turn"
    fake_provider.chat.return_value.tool_calls = []
    fake_provider.chat.return_value.usage = None

    bus = EventBus()
    task_registry = BackgroundTaskRegistry()

    run_id = await spawn_background_subagent(
        provider=fake_provider,
        parent_bus=bus,
        parent_run_id="parent-1",
        permission_manager=None,
        max_steps=5,
        task_registry=task_registry,
        runs_dir=tmp_path,
        session_id="sess-1",
        depth=0,
        description="test task",
        prompt="do something",
    )
    assert isinstance(run_id, str) and run_id
    assert task_registry.get(run_id) is not None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_subagent_tool.py -v`
Expected: FAIL（`ImportError`）

- [ ] **Step 3: 提取函数**

在 `core/subagent/tool.py` 里，`class SpawnAgentTool` 定义之前加模块级函数（把原 `invoke()` 里 `if p.run_in_background:` 分支的创建逻辑原样迁入，注意：不含 `p.subagent_type` 到 `profile` 的解析——那部分留在调用方，函数直接接收已解析好的 `subagent_type` 字符串并在函数内部完成 profile 解析，保持职责单一）：

```python
# 创建并注册一个后台运行的子 agent，返回其 run_id；供 SpawnAgentTool 和 TeamManager 共用
async def spawn_background_subagent(
    *,
    provider: "LLMProvider",
    parent_bus: EventBus,
    parent_run_id: str,
    permission_manager: "PermissionManager | None",
    max_steps: int,
    task_registry: BackgroundTaskRegistry,
    runs_dir: Path,
    session_id: str,
    depth: int,
    description: str,
    prompt: str,
    subagent_type: str = "",
) -> str:
    profile: AgentProfile | None = None
    if subagent_type:
        profile = _profile_loader.load(subagent_type)

    child_run_id = new_run_id()
    child_context = ExecutionContext(
        run_id=child_run_id,
        goal=prompt,
        max_steps=max_steps,
        system_prompt_override=profile.system_prompt if profile else None,
    )

    child_bus = EventBus()

    async def _bridge(event: BaseModel) -> None:
        await parent_bus.publish(event)

    child_bus.subscribe(_bridge)

    # 复用 SpawnAgentTool 实例来构建子 registry，避免重复实现一遍工具过滤逻辑
    builder = SpawnAgentTool(
        provider=provider, parent_bus=parent_bus, parent_run_id=parent_run_id,
        permission_manager=permission_manager, max_steps=max_steps,
        task_registry=task_registry, runs_dir=runs_dir, session_id=session_id, depth=depth,
    )
    child_registry = builder._build_child_registry(child_bus, child_run_id, profile)
    child_loop = AgentLoop(
        provider, child_registry, child_bus,
        permission_manager=permission_manager, session_id=session_id,
    )

    await parent_bus.publish(
        SubagentStartedEvent(
            run_id=child_run_id, parent_run_id=parent_run_id,
            description=description, ts=_now(),
        )
    )

    child_run_path = runs_dir / child_run_id
    child_run_path.mkdir(parents=True, exist_ok=True)

    async def _run() -> None:
        async with EventWriter(child_run_path / "events.jsonl") as writer:
            writer.subscribe(child_bus)
            await child_loop.run(child_context)
        await parent_bus.publish(
            SubagentFinishedEvent(
                run_id=child_run_id, parent_run_id=parent_run_id,
                status=child_context.status, ts=_now(),
            )
        )

    task: asyncio.Task[None] = asyncio.create_task(_run())
    task_registry.register(child_run_id, task, child_context)
    return child_run_id
```

把 `SpawnAgentTool.invoke()` 里原来的 `if p.run_in_background:` 分支替换为：

```python
        if p.run_in_background:
            run_id = await spawn_background_subagent(
                provider=self._provider, parent_bus=self._parent_bus,
                parent_run_id=self._parent_run_id, permission_manager=self._permission_manager,
                max_steps=self._max_steps, task_registry=self._task_registry,
                runs_dir=self._runs_dir, session_id=self._session_id, depth=self._depth,
                description=p.description, prompt=p.prompt, subagent_type=p.subagent_type,
            )
            return ToolResult(
                content=(
                    f"Subagent started in background. run_id={run_id}. "
                    f"Use agent_result(run_id='{run_id}') to retrieve result."
                )
            )
```

（`_depth >= 2` 校验、`profile` 前台分支解析等其余逻辑保持不变。）

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_subagent_tool.py -v`
Expected: PASS

- [ ] **Step 5: 回归既有 subagent 测试**

Run: `uv run pytest tests/unit -k subagent -v`
Expected: 全部通过（确认重构没有改变 `SpawnAgentTool` 原有前台/后台行为）

- [ ] **Step 6: 提交**

```bash
git add src/kivi_agent/core/subagent/tool.py tests/unit/test_subagent_tool.py
git commit -m "refactor: 提取 spawn_background_subagent 共享函数，供 SpawnAgentTool 和 TeamManager 复用"
```

---

### Task F4: TeamManager + team_create 工具

**Files:**
- Create: `src/kivi_agent/core/teams/manager.py`
- Create: `src/kivi_agent/core/tools/builtin/team_create.py`
- Test: `tests/unit/test_team_manager.py`
- Modify: `src/kivi_agent/core/runner.py`
- Modify: `src/kivi_agent/core/permissions/policy.py`

**Interfaces:**
- Consumes: `AgentTeam`/`TeammateInfo`（F1）、`spawn_background_subagent`（F3）
- Produces: `class TeamManager`，`async def create_team(self, goal: str, member_specs: list[dict[str, str]]) -> AgentTeam`、`get_team(team_id: str) -> AgentTeam | None`；`class TeamCreateTool(BaseTool)`，`name = "team_create"`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_team_manager.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.subagent.registry import BackgroundTaskRegistry
from kivi_agent.core.teams.manager import TeamManager


# 功能：验证 create_team 为每个 member_spec 各起一个后台 subagent，并把 run_id 正确关联进团队成员
# 设计：断言团队里的成员数量、名字、角色都和输入一致，且每个成员的 run_id 在 task_registry 里能查到，
#      覆盖"团队创建 = 批量 spawn + 元数据记录"这个核心行为
async def test_create_team_spawns_all_members(tmp_path: Path) -> None:
    fake_provider = AsyncMock()
    fake_provider.chat.return_value.text = "done"
    fake_provider.chat.return_value.stop_reason = "end_turn"
    fake_provider.chat.return_value.tool_calls = []
    fake_provider.chat.return_value.usage = None

    manager = TeamManager(
        provider=fake_provider, bus=EventBus(), permission_manager=None,
        max_steps=5, task_registry=BackgroundTaskRegistry(), runs_dir=tmp_path, session_id="sess-1",
    )
    team = await manager.create_team(
        goal="重构登录模块",
        member_specs=[
            {"name": "planner", "role": "planner", "prompt": "制定计划"},
            {"name": "executor", "role": "executor", "prompt": "执行改动"},
        ],
    )
    assert team.goal == "重构登录模块"
    assert len(team.members) == 2
    assert {m.name for m in team.members} == {"planner", "executor"}
    assert all(m.run_id for m in team.members)


# 功能：验证创建后可以通过 get_team 查回同一个团队对象
# 设计：team_status/team_message 工具都要按 team_id 查团队，覆盖这个基本存取路径
async def test_get_team_returns_created_team(tmp_path: Path) -> None:
    fake_provider = AsyncMock()
    fake_provider.chat.return_value.text = "done"
    fake_provider.chat.return_value.stop_reason = "end_turn"
    fake_provider.chat.return_value.tool_calls = []
    fake_provider.chat.return_value.usage = None

    manager = TeamManager(
        provider=fake_provider, bus=EventBus(), permission_manager=None,
        max_steps=5, task_registry=BackgroundTaskRegistry(), runs_dir=tmp_path, session_id="sess-1",
    )
    team = await manager.create_team(goal="g", member_specs=[{"name": "a", "role": "executor", "prompt": "p"}])
    assert manager.get_team(team.id) is team
    assert manager.get_team("nonexistent") is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_team_manager.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 TeamManager**

```python
# src/kivi_agent/core/teams/manager.py
from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.subagent.registry import BackgroundTaskRegistry
from kivi_agent.core.subagent.tool import spawn_background_subagent
from kivi_agent.core.teams.models import AgentTeam, TeammateInfo

if TYPE_CHECKING:
    from kivi_agent.core.llm.base import LLMProvider
    from kivi_agent.core.permissions.manager import PermissionManager


class TeamManager:
    # 初始化团队管理器，持有创建子 agent 所需的全部依赖（与 SpawnAgentTool 构造参数一致）
    def __init__(
        self,
        *,
        provider: LLMProvider,
        bus: EventBus,
        permission_manager: PermissionManager | None,
        max_steps: int,
        task_registry: BackgroundTaskRegistry,
        runs_dir: Path,
        session_id: str,
    ) -> None:
        self._provider = provider
        self._bus = bus
        self._permission_manager = permission_manager
        self._max_steps = max_steps
        self._task_registry = task_registry
        self._runs_dir = runs_dir
        self._session_id = session_id
        self._teams: dict[str, AgentTeam] = {}

    # 为每个 member_spec 创建一个后台子 agent，组装成一个 AgentTeam 并保存
    async def create_team(self, goal: str, member_specs: list[dict[str, str]]) -> AgentTeam:
        team_id = f"team-{uuid.uuid4().hex[:8]}"
        members: list[TeammateInfo] = []
        for spec in member_specs:
            run_id = await spawn_background_subagent(
                provider=self._provider, parent_bus=self._bus, parent_run_id=team_id,
                permission_manager=self._permission_manager, max_steps=self._max_steps,
                task_registry=self._task_registry, runs_dir=self._runs_dir,
                session_id=self._session_id, depth=0,
                description=f"team member: {spec['name']}", prompt=spec["prompt"],
                subagent_type=spec.get("role", ""),
            )
            members.append(TeammateInfo(name=spec["name"], role=spec.get("role", ""), run_id=run_id))
        team = AgentTeam(id=team_id, goal=goal, members=members)
        self._teams[team_id] = team
        return team

    # 按 team_id 查找团队；不存在返回 None
    def get_team(self, team_id: str) -> AgentTeam | None:
        return self._teams.get(team_id)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_team_manager.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 实现 TeamCreateTool**

```python
# src/kivi_agent/core/tools/builtin/team_create.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.teams.manager import TeamManager
from kivi_agent.core.tools.base import BaseTool, ToolResult


class MemberSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    role: str = ""
    prompt: str


class TeamCreateParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    goal: str
    members: list[MemberSpec]


class TeamCreateTool(BaseTool):
    params_model = TeamCreateParams
    name = "team_create"
    category = "other"
    description = (
        "Create a team of background sub-agents that work in parallel toward a shared goal. "
        "Each member gets its own prompt and optional role (planner/executor/reviewer). "
        "Members run independently — use team_message to coordinate between them and "
        "team_status to check overall progress."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "Overall goal the team is working toward."},
            "members": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "role": {"type": "string", "description": "planner|executor|reviewer|coordinator"},
                        "prompt": {"type": "string"},
                    },
                    "required": ["name", "prompt"],
                },
            },
        },
        "required": ["goal", "members"],
    }

    # 注入 TeamManager，负责实际创建团队
    def __init__(self, team_manager: TeamManager) -> None:
        self._team_manager = team_manager

    # 创建团队并返回团队 ID 与各成员 run_id 摘要
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = TeamCreateParams.model_validate(params)
        team = await self._team_manager.create_team(
            p.goal, [m.model_dump() for m in p.members]
        )
        lines = [f"team_id={team.id}"] + [
            f"  - {m.name} ({m.role}): run_id={m.run_id}" for m in team.members
        ]
        return ToolResult(content="\n".join(lines))
```

- [ ] **Step 6: 注册工具与权限策略**

`policy.py`：`"team_create": ToolPolicy(default=PermissionDecision.ASK),`（会真实起多个后台 LLM 调用，产生成本，默认需要审批）

`runner.py::_build_registry()`（在已有 `provider is not None and bus is not None` 分支附近，与 `spawn_agent` 同一处）：

```python
if _ok("team_create"):
    team_manager = TeamManager(
        provider=provider, bus=bus, permission_manager=self._permission_manager,
        max_steps=self._config.agent.max_steps, task_registry=self._task_registry,
        runs_dir=runs_dir, session_id=session_id,
    )
    registry.register(TeamCreateTool(team_manager))
```

（`team_manager` 实例需要在 `AgentRunner` 层面保持跨 `_build_registry()` 调用持久化，才能让同一个 run 内后续调用 `team_status`/`team_message` 查到之前创建的团队——参考 `self._task_registry` 的做法，在 `AgentRunner.__init__` 里新增 `self._team_manager` 一次性构造，`_build_registry()` 直接引用它而不是每次新建。）

- [ ] **Step 7: 提交**

```bash
git add src/kivi_agent/core/teams/manager.py src/kivi_agent/core/tools/builtin/team_create.py \
        tests/unit/test_team_manager.py src/kivi_agent/core/runner.py src/kivi_agent/core/permissions/policy.py
git commit -m "feat: 新增 TeamManager 与 team_create 工具"
```

---

### Task F5: team_message 工具

**Files:**
- Create: `src/kivi_agent/core/tools/builtin/team_message.py`
- Test: `tests/unit/test_team_message_tool.py`
- Modify: `src/kivi_agent/core/runner.py`
- Modify: `src/kivi_agent/core/permissions/policy.py`

**Interfaces:**
- Consumes: `write_message`/`consume_messages`（F2）、`TeamManager.get_team`（F4）
- Produces: `class TeamMessageTool(BaseTool)`，`name = "team_message"`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_team_message_tool.py
from __future__ import annotations

from pathlib import Path

from kivi_agent.core.teams.mailbox import consume_messages
from kivi_agent.core.tools.builtin.team_message import TeamMessageTool


# 功能：验证工具调用后消息真的写进了对应收件人的 mailbox
# 设计：调用工具后直接用 mailbox 的读取函数验证落盘内容，覆盖"工具是 mailbox.write_message 的薄封装"这一层
async def test_team_message_writes_to_mailbox(tmp_path: Path) -> None:
    tool = TeamMessageTool(mailbox_root=tmp_path)
    result = await tool.invoke({"to": "executor", "sender": "planner", "content": "先看 auth.py"})
    assert not result.is_error
    messages = consume_messages(tmp_path, "executor")
    assert messages[0]["content"] == "先看 auth.py"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_team_message_tool.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/tools/builtin/team_message.py
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.teams.mailbox import write_message
from kivi_agent.core.tools.base import BaseTool, ToolResult


class TeamMessageParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    to: str
    sender: str
    content: str


class TeamMessageTool(BaseTool):
    params_model = TeamMessageParams
    name = "team_message"
    category = "other"
    description = (
        "Send a message to another team member by name. The recipient will see it the next "
        "time it checks its mailbox (sub-agents should call this tool themselves to check in)."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient member name."},
            "sender": {"type": "string", "description": "Your own member name."},
            "content": {"type": "string", "description": "Message content."},
        },
        "required": ["to", "sender", "content"],
    }

    # 注入 mailbox 根目录（通常是 session 的 runs 目录）
    def __init__(self, mailbox_root: Path) -> None:
        self._mailbox_root = mailbox_root

    # 把消息写入收件人的 mailbox
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = TeamMessageParams.model_validate(params)
        write_message(self._mailbox_root, recipient=p.to, sender=p.sender, content=p.content)
        return ToolResult(content=f"message sent to {p.to}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_team_message_tool.py -v`
Expected: PASS（1 passed）

- [ ] **Step 5: 注册工具与权限策略**

`policy.py`：`"team_message": ToolPolicy(default=PermissionDecision.ALLOW),`（纯文本消息传递，低风险）

`runner.py`：`if _ok("team_message"): registry.register(TeamMessageTool(mailbox_root=child_runs_dir or self._runs_dir))`

- [ ] **Step 6: 提交**

```bash
git add src/kivi_agent/core/tools/builtin/team_message.py tests/unit/test_team_message_tool.py \
        src/kivi_agent/core/runner.py src/kivi_agent/core/permissions/policy.py
git commit -m "feat: 新增 team_message 工具，团队成员间可寻址通信"
```

---

### Task F6: 协调者角色约束（复用 allowed_tools 白名单）

**Files:**
- Create: `src/kivi_agent/core/agents/builtin/coordinator.toml`
- Test: `tests/unit/test_agent_profile_loader.py`（追加用例）

**Interfaces:**
- Consumes: 已有 `AgentProfileLoader`（`core/agents/loader.py`，本任务不改代码，只加一个内建 profile 文件）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_agent_profile_loader.py 追加
from kivi_agent.core.agents.loader import AgentProfileLoader


# 功能：验证内建 coordinator 角色的 allowed_tools 不含任何写操作工具（write_file/edit_file/bash）
# 设计："协调者只调度不编码"这个约束的验收标准就是白名单里没有写类工具，
#      覆盖配置文件本身而不是运行时行为——运行时行为已经由 _build_child_registry 的
#      _allowed() 过滤机制保证，这里只需确认配置内容正确
def test_coordinator_profile_excludes_write_tools() -> None:
    loader = AgentProfileLoader()
    profile = loader.load("coordinator")
    assert profile is not None
    forbidden = {"write_file", "edit_file", "bash"}
    assert forbidden.isdisjoint(set(profile.allowed_tools))
    assert "team_create" in profile.allowed_tools
    assert "team_message" in profile.allowed_tools
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_agent_profile_loader.py -k coordinator -v`
Expected: FAIL（`profile is None`）

- [ ] **Step 3: 新建 profile 文件**

先看一个现有内建 profile（如 `core/agents/builtin/planner.toml`）确认字段格式，再按同样结构写：

```toml
# src/kivi_agent/core/agents/builtin/coordinator.toml
system_prompt = """
You are a coordinator agent. Your job is to break down complex goals into sub-tasks, \
create teams via team_create, monitor progress via team_status, and relay information \
between members via team_message. You do not write or edit code yourself — delegate \
implementation work to executor sub-agents.
"""
allowed_tools = [
    "read_file", "list_dir", "glob", "grep",
    "team_create", "team_message", "team_status",
    "agent_result", "task_create", "task_update", "task_list", "task_get",
]
```

（若现有 planner.toml 的 TOML 顶层字段名或结构与上面不同——比如是 `[agent]` 表而不是顶层字段——按现有文件的实际格式对齐，不要凭空假设。）

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_agent_profile_loader.py -k coordinator -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/kivi_agent/core/agents/builtin/coordinator.toml tests/unit/test_agent_profile_loader.py
git commit -m "feat: 新增 coordinator 内建角色，只调度不编码"
```

---

### Task F7: team_status 查询工具

**Files:**
- Create: `src/kivi_agent/core/tools/builtin/team_status.py`
- Test: `tests/unit/test_team_status_tool.py`
- Modify: `src/kivi_agent/core/runner.py`
- Modify: `src/kivi_agent/core/permissions/policy.py`

**Interfaces:**
- Consumes: `TeamManager.get_team`（F4）、`BackgroundTaskRegistry.get`（已有）
- Produces: `class TeamStatusTool(BaseTool)`，`name = "team_status"`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_team_status_tool.py
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.subagent.registry import BackgroundTaskRegistry
from kivi_agent.core.teams.manager import TeamManager
from kivi_agent.core.tools.builtin.team_status import TeamStatusTool


# 功能：验证查询一个刚创建、还在跑的团队时，每个成员状态显示为运行中而不是报错
# 设计：真实起了后台 asyncio.Task（还没被 await 完成），断言输出里包含每个成员名字和"running"类状态描述，
#      覆盖"团队还没完成时查询也应该给出有意义信息"这个场景
async def test_team_status_reports_running_members(tmp_path: Path) -> None:
    fake_provider = AsyncMock()

    async def _slow_chat(*args, **kwargs):
        import asyncio
        await asyncio.sleep(10)  # 不会真的等完，测试里会在这之前查询状态

    fake_provider.chat.side_effect = _slow_chat

    task_registry = BackgroundTaskRegistry()
    manager = TeamManager(
        provider=fake_provider, bus=EventBus(), permission_manager=None,
        max_steps=5, task_registry=task_registry, runs_dir=tmp_path, session_id="sess-1",
    )
    team = await manager.create_team(goal="g", member_specs=[{"name": "a", "role": "executor", "prompt": "p"}])

    tool = TeamStatusTool(manager)
    result = await tool.invoke({"team_id": team.id})
    assert not result.is_error
    assert "a" in result.content
    assert "running" in result.content.lower()


# 功能：验证查询不存在的 team_id 返回明确错误而不是抛异常
# 设计：覆盖"team_id 打错了"这个用户输入错误场景
async def test_team_status_unknown_team_returns_error(tmp_path: Path) -> None:
    from unittest.mock import MagicMock
    manager = TeamManager(
        provider=MagicMock(), bus=EventBus(), permission_manager=None,
        max_steps=5, task_registry=BackgroundTaskRegistry(), runs_dir=tmp_path, session_id="sess-1",
    )
    tool = TeamStatusTool(manager)
    result = await tool.invoke({"team_id": "nonexistent"})
    assert result.is_error
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_team_status_tool.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/core/tools/builtin/team_status.py
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.teams.manager import TeamManager
from kivi_agent.core.tools.base import BaseTool, ToolResult


class TeamStatusParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    team_id: str


class TeamStatusTool(BaseTool):
    params_model = TeamStatusParams
    name = "team_status"
    category = "read"
    description = "Check the progress of all members in a team created by team_create."
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {"team_id": {"type": "string"}},
        "required": ["team_id"],
    }

    # 注入 TeamManager，用于按 team_id 查询团队和各成员的后台任务状态
    def __init__(self, team_manager: TeamManager) -> None:
        self._team_manager = team_manager

    # 汇总团队每个成员的后台任务状态，返回可读的进度摘要
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = TeamStatusParams.model_validate(params)
        team = self._team_manager.get_team(p.team_id)
        if team is None:
            return ToolResult(
                content=f"unknown team_id: {p.team_id}", is_error=True, error_type="runtime_error"
            )

        lines = [f"team {team.id}: {team.goal}"]
        for member in team.members:
            entry = self._team_manager._task_registry.get(member.run_id)
            if entry is None:
                status = "unknown"
            else:
                task, _ = entry
                status = "running" if not task.done() else ("failed" if task.exception() else "success")
            lines.append(f"  - {member.name} ({member.role}): {status}")
        return ToolResult(content="\n".join(lines))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_team_status_tool.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 注册工具与权限策略、全量回归**

`policy.py`：`"team_status": ToolPolicy(default=PermissionDecision.ALLOW),`
`runner.py`：`if _ok("team_status"): registry.register(TeamStatusTool(self._team_manager))`

Run: `uv run pytest tests/unit -v`
Run: `uv run ruff check src tests`
Run: `uv run mypy src`
Expected: 全部通过

- [ ] **Step 6: 提交**

```bash
git add src/kivi_agent/core/tools/builtin/team_status.py tests/unit/test_team_status_tool.py \
        src/kivi_agent/core/runner.py src/kivi_agent/core/permissions/policy.py
git commit -m "feat: 新增 team_status 工具，汇总团队成员进度"
```

---

## Self-Review Notes

- **覆盖范围**：F1-F7 覆盖 M32（团队模型）、M33（协调者约束，用现有白名单机制而非新协调者代码）、M34（成员通信/mailbox）、M35（团队工具）、M36（子 Agent 隔离——本包只做团队与通信，工作树隔离见下方说明）。
- **子 Agent 工作树隔离（原 M36 的另一半）未包含在本包**：`spawn_background_subagent` 目前不会自动给子 agent 分配独立工作树。这是刻意的范围裁剪——工作树隔离对"团队并行改代码"才有意义，而验证团队机制本身（创建、通信、状态查询）不需要它。如果后续要让团队成员真正并行改同一个仓库而不冲突，需要在 `spawn_background_subagent` 里加一个 `isolate_worktree: bool` 参数，接入基础闭环已有的 `create_worktree`/`remove_worktree`——建议作为独立的小任务在 F1-F7 验收通过后再做，而不是现在就塞进去增加本包复杂度。
- **类型一致性**：`spawn_background_subagent`（F3）的返回类型 `str`（run_id）在 F4 的 `TeamManager.create_team` 里原样使用；`TeamManager` 的构造参数在 F4/F7 两处工具里保持同一份依赖注入方式，与 `runner.py` 里 `self._team_manager` 单例模式一致，不会出现"每次调用都新建一个空的 TeamManager 导致查不到之前创建的团队"这类错误。
