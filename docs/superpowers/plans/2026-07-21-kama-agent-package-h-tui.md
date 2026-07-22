# kamaAgent 包H：TUI 增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 TUI 加三块能力：① 会话列表/恢复界面（消费包 E 的检查点数据）；② 计划模式对话框（消费包 D 的 `PermissionMode.PLAN`）；③ 团队树视图（消费包 F 的 `TeamManager`）。第一步先把现有单文件 `tui/app.py`（1000+ 行）里已经存在的 `PermissionSelect`/`PermissionBlock` 拆到独立文件，为后续新增组件腾出干净的落点。

**Architecture:** 计划模式需要新的协议命令（daemon 侧要接收"切换权限模式"的请求），走仓库已有的 JSON-RPC 命令模式（`core/bus/commands.py` 加新 `Command`，`core/app.py` 加 handler，回归 `scripts/gen_protocol_doc.py` 生成文档）。团队树复用已有的 `SubagentStartedEvent`/`SubagentFinishedEvent`（这两个事件本来就在 `spawn_background_subagent` 里发布），只需要新增一个 `TeamCreatedEvent` 让 TUI 知道"团队有哪些成员、team_id 是什么"这层映射关系。会话列表纯读取本地文件（`SessionStore`/`CheckpointStore`），不需要新协议。

**Tech Stack:** Python 3.12、Textual、pydantic v2（协议模型）、pytest + pytest-asyncio、uv。

## Global Constraints

- 遵守仓库 `CLAUDE.md`：每个函数上方一行中文注释；每个测试函数上方两行中文注释（`# 功能：`/`# 设计：`）。
- 测试命令：`uv run pytest tests/unit/test_xxx.py -v`；全量回归：`uv run pytest tests/unit -v`。
- **改动 `core/bus/commands.py`/`core/bus/events.py` 后必须重新生成协议文档**：`uv run python scripts/gen_protocol_doc.py`，并 `git add WIRE_PROTOCOL.md` 一并提交；提交前先用 `uv run python scripts/gen_protocol_doc.py --check` 确认未提交时文档会报不一致（验证生成脚本确实感知到了改动）。
- **本包依赖包 E（`CheckpointStore`）和包 F（`TeamManager`/事件桥接机制）**，两者都已在 Wave 1/2 合入 `integration/wave1`，可以直接 import，不需要再确认。
- **TUI 单文件拆分只搬迁代码，不改行为**——H1 完成后必须跑一次现有 TUI 测试全量回归，确认拆分是纯重构。

---

### Task H1: 拆分 PermissionSelect/PermissionBlock 到独立文件

**Files:**
- Create: `src/kivi_agent/tui/permission_widgets.py`
- Modify: `src/kivi_agent/tui/app.py`
- Test: `tests/unit/test_tui_app.py`（确认既有测试全部通过，不新增测试——这是纯重构）

**Interfaces:**
- Produces: `tui/permission_widgets.py` 导出 `PermissionSelect`、`PermissionBlock`（类定义原样迁移）

- [ ] **Step 1: 迁移前先跑一次基线测试**

Run: `uv run pytest tests/unit/test_tui_app.py -v`
Expected: 全部通过（记录当前 passed 数量，作为迁移后比对基线）

- [ ] **Step 2: 原样迁移两个类**

把 `tui/app.py` 里 `class PermissionSelect(Static):`（约第 172 行）到 `class PermissionBlock(Static):`（约第 278 行）结束的完整代码块，剪切到新文件：

```python
# src/kivi_agent/tui/permission_widgets.py
from __future__ import annotations

# 从 app.py 迁移，导入语句按实际用到的做精简（events/Message/Static 等 Textual 组件，
# 以及 PermissionSelect/PermissionBlock 内部用到的其它类型）——
# 迁移时逐一确认 app.py 顶部哪些 import 是这两个类专属的，同步搬过来
...
# （PermissionSelect 和 PermissionBlock 的完整类定义原样粘贴于此）
```

在 `tui/app.py` 顶部加：

```python
from kivi_agent.tui.permission_widgets import PermissionBlock, PermissionSelect
```

- [ ] **Step 3: 运行测试确认拆分未破坏行为**

Run: `uv run pytest tests/unit/test_tui_app.py -v`
Expected: 全部通过，通过数量与 Step 1 记录的基线一致

Run: `uv run ruff check src/kivi_agent/tui/`
Run: `uv run mypy src/kivi_agent/tui/`
Expected: 无新增问题

- [ ] **Step 4: 提交**

```bash
cd "/Users/kivi/Documents/agent系统/Kama/kivi-agent"
git add src/kivi_agent/tui/app.py src/kivi_agent/tui/permission_widgets.py
git commit -m "refactor: 拆分 PermissionSelect/PermissionBlock 到独立文件"
```

---

### Task H2: SessionStore.list_sessions()

**Files:**
- Modify: `src/kivi_agent/core/session/store.py`
- Test: `tests/unit/test_session_store.py`（追加用例）

**Interfaces:**
- Produces: `SessionStore.list_sessions() -> list[Session]`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_session_store.py 追加
# 功能：验证 list_sessions 能枚举出所有已创建的 session，按 updated_at 倒序排列
# 设计：创建两个 session（写 meta.json），断言列表包含两者且更晚更新的排在前面，
#      覆盖"会话选择界面应该把最近用过的会话排在最上面"这个使用场景
def test_list_sessions_returns_all_sorted_by_recency(tmp_path):
    from kivi_agent.core.session.model import Session
    store = SessionStore(tmp_path)
    store.write_meta(Session(
        id="s1", mode="chat", status="active", title="old",
        created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:00+00:00",
    ))
    store.write_meta(Session(
        id="s2", mode="chat", status="active", title="new",
        created_at="2026-01-02T00:00:00+00:00", updated_at="2026-01-02T00:00:00+00:00",
    ))
    sessions = store.list_sessions()
    assert [s.id for s in sessions] == ["s2", "s1"]


# 功能：验证没有任何 session 时返回空列表而不是报错
# 设计：全新的 root 目录，覆盖首次使用 TUI 会话列表界面时的空状态
def test_list_sessions_empty_when_none_exist(tmp_path):
    store = SessionStore(tmp_path)
    assert store.list_sessions() == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_session_store.py -k list_sessions -v`
Expected: FAIL（`AttributeError`）

- [ ] **Step 3: 实现**

在 `core/session/store.py::SessionStore` 里加方法：

```python
    # 枚举所有已创建的 session，按 updated_at 倒序返回（最近使用的在前）
    def list_sessions(self) -> list[Session]:
        sessions: list[Session] = []
        if not self._root.exists():
            return sessions
        for meta_path in self._root.glob("*/meta.json"):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                sessions.append(Session.from_dict(data))
            except Exception:
                logger.warning("skip unreadable session meta: %s", meta_path)
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_session_store.py -v`
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
git add src/kivi_agent/core/session/store.py tests/unit/test_session_store.py
git commit -m "feat: SessionStore 加 list_sessions，按最近使用排序"
```

---

### Task H3: Session 选择/恢复 Screen

**Files:**
- Create: `src/kivi_agent/tui/session_screen.py`
- Test: `tests/unit/test_session_screen.py`

**Interfaces:**
- Consumes: `SessionStore.list_sessions()`（H2）、`CheckpointStore.load()`（包 E 已有）
- Produces: `def format_session_row(session: Session, checkpoint: CheckpointData | None) -> str`（纯函数，供 Screen 渲染每一行，独立可测）；`class SessionListScreen(Screen)`

- [ ] **Step 1: 写失败测试（先测纯函数部分，Screen 挂载渲染不做单元测试，交给 H1 一样的"手动 TUI 验收"覆盖）**

```python
# tests/unit/test_session_screen.py
from __future__ import annotations

from kivi_agent.core.session.checkpoint import CheckpointData
from kivi_agent.core.session.model import Session
from kivi_agent.tui.session_screen import format_session_row


# 功能：验证有检查点时，展示行包含 session 标题和检查点的 step/status 信息
# 设计：这是用户在会话列表界面判断"这个会话上次跑到哪一步、能不能继续"的关键信息来源
def test_format_row_with_checkpoint_shows_progress() -> None:
    session = Session(
        id="s1", mode="chat", status="active", title="修复登录 bug",
        created_at="t", updated_at="t",
    )
    checkpoint = CheckpointData(run_id="r1", step=3, status="running", message_count=10, ts="t")
    row = format_session_row(session, checkpoint)
    assert "修复登录 bug" in row
    assert "step 3" in row
    assert "running" in row


# 功能：验证没有检查点时（比如会话从未跑过任何 run）展示行不报错，给出明确的"无进度"提示
# 设计：覆盖新建但还没发过消息的会话这个边界状态
def test_format_row_without_checkpoint_shows_no_progress() -> None:
    session = Session(
        id="s2", mode="chat", status="active", title="新会话",
        created_at="t", updated_at="t",
    )
    row = format_session_row(session, None)
    assert "新会话" in row
    assert "no progress" in row.lower()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_session_screen.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/tui/session_screen.py
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from kivi_agent.core.session.checkpoint import CheckpointData, CheckpointStore
from kivi_agent.core.session.model import Session
from kivi_agent.core.session.store import SessionStore


# 渲染一行会话摘要：标题 + 最近检查点的 step/status（无检查点时给出明确提示）
def format_session_row(session: Session, checkpoint: CheckpointData | None) -> str:
    progress = f"step {checkpoint.step} ({checkpoint.status})" if checkpoint else "no progress yet"
    return f"[bold]{session.title or session.id}[/bold]  [dim]{session.id}[/dim]  {progress}"


class SessionSelected(Static.Message if False else object):  # placeholder removed below
    pass


class SessionListScreen(Screen[None]):
    """列出所有历史会话，选中后触发恢复。"""

    BINDINGS = [Binding("escape", "dismiss", "close")]

    # 注入会话存储和检查点存储
    def __init__(self, session_store: SessionStore, checkpoint_store: CheckpointStore) -> None:
        super().__init__()
        self._session_store = session_store
        self._checkpoint_store = checkpoint_store

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="session-list")

    def on_mount(self) -> None:
        container = self.query_one("#session-list", VerticalScroll)
        sessions = self._session_store.list_sessions()
        if not sessions:
            container.mount(Static("[dim]no sessions yet[/dim]"))
            return
        for session in sessions:
            checkpoint = None
            if session.run_ids:
                checkpoint = self._checkpoint_store.load(session.id, session.run_ids[-1])
            container.mount(Static(format_session_row(session, checkpoint)))
```

（上面 `class SessionSelected` 那行是占位错误写法，Step 4 里必须删掉——正确做法是用 Textual 标准的 `Message` 子类模式定义选中事件，若 Screen 只做只读展示、恢复逻辑走键盘 `Enter` 后调用 `self.dismiss(selected_session_id)` 由调用方处理，不需要自定义 Message 类，实现时按这个更简单的方式做，不要把上面这行占位代码抄进正式实现。）

- [ ] **Step 4: 修正实现，去掉占位代码**

删除 `class SessionSelected` 那段无意义占位。若要支持"选中后恢复"，用 Textual 内建的 `ListView`/`ListItem` 或者给每行 `Static` 加 `can_focus=True` + 键盘事件处理，选中后调用 `self.dismiss(session.id)`——具体交互细节实现时可以先做最小可用版本（只读展示，不支持键盘选择），恢复动作留给用户手动执行 `kivi-tui --replay <run_id>`（已有能力），本任务的核心交付是"能看到所有会话和它们的进度"，交互式选择可以是后续独立的小任务。

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_session_screen.py -v`
Expected: PASS（2 passed，只测 `format_session_row` 纯函数部分）

- [ ] **Step 6: 接入主 App（新增快捷键打开）**

在 `tui/app.py::KamaTuiApp` 的 `BINDINGS` 里加一条：

```python
    BINDINGS = [
        Binding("ctrl+q", "quit", "quit"),
        Binding("ctrl+s", "show_sessions", "sessions"),
    ]
```

加对应 action 方法：

```python
    # 打开会话列表界面
    def action_show_sessions(self) -> None:
        from kivi_agent.core.session.checkpoint import CheckpointStore
        from kivi_agent.core.session.store import SessionStore
        from kivi_agent.tui.session_screen import SessionListScreen

        sessions_root = Path("~/.kivi/sessions").expanduser()
        self.push_screen(SessionListScreen(SessionStore(sessions_root), CheckpointStore(sessions_root)))
```

- [ ] **Step 7: 提交**

```bash
git add src/kivi_agent/tui/session_screen.py src/kivi_agent/tui/app.py tests/unit/test_session_screen.py
git commit -m "feat: 新增会话列表界面，展示历史会话及其检查点进度"
```

---

### Task H4: TeamCreatedEvent

**Files:**
- Modify: `src/kivi_agent/core/bus/events.py`
- Modify: `src/kivi_agent/core/teams/manager.py`
- Test: `tests/unit/test_team_manager.py`（追加用例）

**Interfaces:**
- Produces: `class TeamCreatedEvent(BaseModel)`（`team_id, goal, members: list[dict[str,str]]`）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_team_manager.py 追加
# 功能：验证 create_team 完成后会发布一条 TeamCreatedEvent，携带 team_id 和成员名单
# 设计：TUI 团队树（Task H5）需要订阅这条事件来初始化树结构，覆盖事件确实被发布这一步
async def test_create_team_publishes_team_created_event(tmp_path) -> None:
    from unittest.mock import AsyncMock
    from kivi_agent.core.bus.events import TeamCreatedEvent
    from kivi_agent.core.events.bus import EventBus
    from kivi_agent.core.subagent.registry import BackgroundTaskRegistry
    from kivi_agent.core.teams.manager import TeamManager

    fake_provider = AsyncMock()
    fake_provider.chat.return_value.text = "done"
    fake_provider.chat.return_value.stop_reason = "end_turn"
    fake_provider.chat.return_value.tool_calls = []
    fake_provider.chat.return_value.usage = None

    received: list[object] = []
    bus = EventBus()
    bus.subscribe(lambda e: received.append(e) or _noop())

    async def _noop():
        pass

    manager = TeamManager(
        provider=fake_provider, bus=bus, permission_manager=None,
        max_steps=5, task_registry=BackgroundTaskRegistry(), runs_dir=tmp_path, session_id="sess-1",
    )
    await manager.create_team(goal="g", member_specs=[{"name": "a", "role": "executor", "prompt": "p"}])

    team_events = [e for e in received if isinstance(e, TeamCreatedEvent)]
    assert len(team_events) == 1
    assert team_events[0].goal == "g"
    assert team_events[0].members[0]["name"] == "a"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_team_manager.py -k publishes -v`
Expected: FAIL（`ImportError: cannot import name 'TeamCreatedEvent'`）

- [ ] **Step 3: 加事件定义**

在 `core/bus/events.py`，`SkillInvokedEvent` 定义之后加：

```python
class TeamCreatedEvent(BaseModel):
    type: Literal["team.created"] = "team.created"
    team_id: str
    goal: str
    members: list[dict[str, str]]  # [{"name":, "role":, "run_id":}, ...]
    ts: str
```

在文件末尾的 `Event` 判别联合里加 `| TeamCreatedEvent,`。

- [ ] **Step 4: TeamManager 发布事件**

在 `core/teams/manager.py::create_team()`，`self._teams[team_id] = team` 之后、`return team` 之前加：

```python
        from datetime import UTC, datetime
        from kivi_agent.core.bus.events import TeamCreatedEvent
        await self._bus.publish(
            TeamCreatedEvent(
                team_id=team.id, goal=team.goal,
                members=[{"name": m.name, "role": m.role, "run_id": m.run_id} for m in team.members],
                ts=datetime.now(UTC).isoformat(),
            )
        )
```

- [ ] **Step 5: 运行测试确认通过、重新生成协议文档**

Run: `uv run pytest tests/unit/test_team_manager.py -v`
Expected: 全部通过

Run: `uv run python scripts/gen_protocol_doc.py`
Run: `uv run python scripts/gen_protocol_doc.py --check`
Expected: 无差异（生成后即一致）

- [ ] **Step 6: 提交**

```bash
git add src/kivi_agent/core/bus/events.py src/kivi_agent/core/teams/manager.py \
        tests/unit/test_team_manager.py WIRE_PROTOCOL.md
git commit -m "feat: 团队创建时发布 TeamCreatedEvent，供 TUI 团队树消费"
```

---

### Task H5: 团队树 Widget

**Files:**
- Create: `src/kivi_agent/tui/team_tree.py`
- Test: `tests/unit/test_team_tree.py`

**Interfaces:**
- Consumes: `TeamCreatedEvent`（H4）、`SubagentStartedEvent`/`SubagentFinishedEvent`（已有）
- Produces: `class TeamTreeState`（纯状态类，独立可测，不依赖 Textual 挂载）、`class TeamTreeWidget(Static)`

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_team_tree.py
from __future__ import annotations

from kivi_agent.tui.team_tree import TeamTreeState


# 功能：验证收到 TeamCreatedEvent 后，状态里出现对应团队和全部成员，初始状态为 "pending"
# 设计：团队树的数据模型和事件订阅逻辑分离测试，不需要真的挂载 Textual 组件
def test_state_registers_team_on_created_event() -> None:
    state = TeamTreeState()
    state.on_team_created(
        team_id="team-1", goal="g",
        members=[{"name": "a", "role": "executor", "run_id": "run-1"}],
    )
    assert "team-1" in state.teams
    assert state.teams["team-1"].members[0].status == "pending"


# 功能：验证收到 SubagentStartedEvent/SubagentFinishedEvent 后，对应成员状态被更新
# 设计：按 run_id 匹配到具体成员并更新其 status，覆盖团队树"实时反映进度"这个核心价值
def test_state_updates_member_status_on_subagent_events() -> None:
    state = TeamTreeState()
    state.on_team_created(
        team_id="team-1", goal="g",
        members=[{"name": "a", "role": "executor", "run_id": "run-1"}],
    )
    state.on_subagent_started(run_id="run-1")
    assert state.teams["team-1"].find_member("a").status == "running"

    state.on_subagent_finished(run_id="run-1", status="success")
    assert state.teams["team-1"].find_member("a").status == "success"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_team_tree.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现状态类**

```python
# src/kivi_agent/tui/team_tree.py
from __future__ import annotations

from textual.widgets import Static

from kivi_agent.core.teams.models import AgentTeam, TeammateInfo


class TeamTreeState:
    # 初始化空的团队状态表，以及 run_id -> team_id 的反查索引（用于处理 subagent 事件时定位团队）
    def __init__(self) -> None:
        self.teams: dict[str, AgentTeam] = {}
        self._run_to_team: dict[str, str] = {}

    # 处理 team.created 事件：注册团队及全部成员，建立 run_id 反查索引
    def on_team_created(self, *, team_id: str, goal: str, members: list[dict[str, str]]) -> None:
        team_members = [
            TeammateInfo(name=m["name"], role=m["role"], run_id=m["run_id"]) for m in members
        ]
        self.teams[team_id] = AgentTeam(id=team_id, goal=goal, members=team_members)
        for m in team_members:
            self._run_to_team[m.run_id] = team_id

    # 处理 subagent.started 事件：把对应成员状态置为 running
    def on_subagent_started(self, *, run_id: str) -> None:
        self._update_member_status(run_id, "running")

    # 处理 subagent.finished 事件：把对应成员状态置为最终状态
    def on_subagent_finished(self, *, run_id: str, status: str) -> None:
        self._update_member_status(run_id, status)

    # 按 run_id 反查团队和成员，更新其状态；找不到（非团队成员的普通子 agent）时静默忽略
    def _update_member_status(self, run_id: str, status: str) -> None:
        team_id = self._run_to_team.get(run_id)
        if team_id is None:
            return
        team = self.teams[team_id]
        for member in team.members:
            if member.run_id == run_id:
                member.status = status
                return


_STATUS_ICON = {"pending": "○", "running": "◐", "success": "●", "failed": "✗"}


class TeamTreeWidget(Static):
    """展示所有团队及其成员的实时状态树。"""

    # 初始化，持有共享的状态对象（由 KamaTuiApp 在事件分发时统一更新）
    def __init__(self, state: TeamTreeState) -> None:
        super().__init__()
        self._state = state

    # 根据当前状态重新渲染整棵树
    def refresh_tree(self) -> None:
        lines: list[str] = []
        for team in self._state.teams.values():
            lines.append(f"[bold]{team.id}[/bold]  {team.goal}")
            for member in team.members:
                icon = _STATUS_ICON.get(member.status, "?")
                lines.append(f"  {icon} {member.name} ({member.role})")
        self.update("\n".join(lines) if lines else "[dim]no teams yet[/dim]")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_team_tree.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 接入 KamaTuiApp 事件分发**

在 `tui/app.py` 的事件处理方法（`_handle_event` 或等价的按 `event["type"]` 分发的函数）里加：

```python
        elif t == "team.created":
            self._team_tree_state.on_team_created(
                team_id=event["team_id"], goal=event["goal"], members=event["members"],
            )
            self._refresh_team_tree_if_mounted()
        elif t == "subagent.started":
            self._team_tree_state.on_subagent_started(run_id=event["run_id"])
            self._refresh_team_tree_if_mounted()
        elif t == "subagent.finished":
            self._team_tree_state.on_subagent_finished(run_id=event["run_id"], status=event["status"])
            self._refresh_team_tree_if_mounted()
```

在 `KamaTuiApp.__init__` 加 `self._team_tree_state = TeamTreeState()`，并添加一个辅助方法：

```python
    # 若团队树组件已挂载则刷新其展示；未挂载（用户还没打开）时跳过
    def _refresh_team_tree_if_mounted(self) -> None:
        try:
            self.query_one(TeamTreeWidget).refresh_tree()
        except NoMatches:
            pass
```

（是否常驻挂载 `TeamTreeWidget` 还是像 `SessionListScreen` 一样按需 push_screen 打开，取决于当前 TUI 布局空间——建议做成一个可以用快捷键切换显隐的侧边栏，具体挂载方式实现时根据 `compose()` 现有布局决定，不强制规定。）

- [ ] **Step 6: 提交**

```bash
git add src/kivi_agent/tui/team_tree.py src/kivi_agent/tui/app.py tests/unit/test_team_tree.py
git commit -m "feat: 新增团队树视图，实时展示团队成员状态"
```

---

### Task H6: 计划模式协议命令

**Files:**
- Modify: `src/kivi_agent/core/bus/commands.py`
- Modify: `src/kivi_agent/core/app.py`
- Test: `tests/unit/test_commands_events.py`（追加用例，或按现有测试组织方式新建）

**Interfaces:**
- Produces: `class SetPermissionModeCommand(BaseModel)`（`session_id: str, mode: str`）、`class SetPermissionModeResult(BaseModel)`（`ok: bool`）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_commands_events.py 追加（或新建 tests/unit/test_set_permission_mode.py）
# 功能：验证 SetPermissionModeCommand 能正常序列化/反序列化，type 字段固定
# 设计：和仓库里其它 Command 模型一样的判别联合契约测试，确保新命令能被正确路由
def test_set_permission_mode_command_roundtrip() -> None:
    from kivi_agent.core.bus.commands import SetPermissionModeCommand
    cmd = SetPermissionModeCommand(session_id="sess-1", mode="bypass")
    data = cmd.model_dump()
    assert data["type"] == "permission.set_mode"
    restored = SetPermissionModeCommand.model_validate(data)
    assert restored.mode == "bypass"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_commands_events.py -k set_permission_mode -v`
Expected: FAIL（`ImportError`）

- [ ] **Step 3: 加命令模型**

在 `core/bus/commands.py`，`PermissionRespondResult` 定义之后加：

```python
class SetPermissionModeCommand(BaseModel):
    type: Literal["permission.set_mode"] = "permission.set_mode"
    session_id: str
    mode: str  # "default" | "accept_edits" | "plan" | "bypass"


class SetPermissionModeResult(BaseModel):
    ok: bool = True
```

把 `SetPermissionModeCommand` 加入文件末尾的 `Command` 判别联合。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_commands_events.py -v`
Expected: PASS

- [ ] **Step 5: app.py 加 handler**

参考 `_permission_respond_handler` 的写法，在 `core/app.py` 加：

```python
    # 切换指定 session 的权限模式（DEFAULT/ACCEPT_EDITS/PLAN/BYPASS）
    async def _set_permission_mode_handler(self, params: dict[str, Any]) -> SetPermissionModeResult:
        cmd = SetPermissionModeCommand.model_validate(params)
        if self._permission_manager is None:
            logger.error("permission.set_mode: PermissionManager not initialized")
            return SetPermissionModeResult(ok=False)
        try:
            mode = PermissionMode(cmd.mode)
        except ValueError:
            logger.warning("permission.set_mode: invalid mode %r", cmd.mode)
            return SetPermissionModeResult(ok=False)
        self._permission_manager.set_mode(mode)
        logger.info("permission mode changed to %s (session=%s)", mode.value, cmd.session_id)
        return SetPermissionModeResult(ok=True)
```

在 handler 注册列表（`server.register(...)` 那一段）加：

```python
        server.register("permission.set_mode", self._set_permission_mode_handler)
```

顶部补 import：`from kivi_agent.core.bus.commands import SetPermissionModeCommand, SetPermissionModeResult`、`from kivi_agent.core.permissions.modes import PermissionMode`。

- [ ] **Step 6: 重新生成协议文档并回归**

Run: `uv run python scripts/gen_protocol_doc.py`

Run: `uv run pytest tests/unit -v`
Run: `uv run ruff check src tests`
Run: `uv run mypy src`
Expected: 全部通过

- [ ] **Step 7: 提交**

```bash
git add src/kivi_agent/core/bus/commands.py src/kivi_agent/core/app.py \
        tests/unit/test_commands_events.py WIRE_PROTOCOL.md
git commit -m "feat: 新增 permission.set_mode 协议命令，支持客户端切换权限模式"
```

---

### Task H7: 计划模式对话框

**Files:**
- Create: `src/kivi_agent/tui/plan_dialog.py`
- Test: `tests/unit/test_plan_dialog.py`

**Interfaces:**
- Consumes: `exit_plan_mode` 工具产出的 `plan_summary` 文本（通过 `tool.finished` 事件的 `output` 字段拿到，工具名匹配 `exit_plan_mode` 时触发）、`SetPermissionModeCommand`（H6）
- Produces: `class PlanChoice`（`Literal["accept", "reject"]` 或等价枚举）、`def parse_plan_summary(tool_output: str) -> str`（从 `exit_plan_mode` 工具的输出文本里提取纯计划摘要，去掉包装文案）

- [ ] **Step 1: 写失败测试**

```python
# tests/unit/test_plan_dialog.py
from __future__ import annotations

from kivi_agent.tui.plan_dialog import parse_plan_summary


# 功能：验证从 exit_plan_mode 工具的标准输出文本里正确提取出纯计划内容
# 设计：exit_plan_mode.py（包 D）的输出格式是固定的
#      "Plan ready for review:\n\n{summary}\n\nAwaiting user decision."，
#      对话框只需要中间那部分，覆盖这个字符串提取逻辑
def test_parse_plan_summary_extracts_middle_content() -> None:
    tool_output = "Plan ready for review:\n\n先加测试再实现\n\nAwaiting user decision."
    assert parse_plan_summary(tool_output) == "先加测试再实现"


# 功能：验证输出格式不符合预期时，原样返回整段文本而不是抛异常或返回空
# 设计：容错兜底——格式万一变了，对话框至少还能展示点什么，而不是白屏
def test_parse_plan_summary_falls_back_to_raw_text_on_mismatch() -> None:
    assert parse_plan_summary("unexpected format") == "unexpected format"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/unit/test_plan_dialog.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

```python
# src/kivi_agent/tui/plan_dialog.py
from __future__ import annotations

import re

from textual.containers import Vertical
from textual.widgets import Button, Static

_PLAN_OUTPUT_RE = re.compile(
    r"^Plan ready for review:\n\n(.*)\n\nAwaiting user decision\.$", re.DOTALL
)


# 从 exit_plan_mode 工具的标准输出文本里提取纯计划内容；格式不匹配时原样返回整段文本
def parse_plan_summary(tool_output: str) -> str:
    match = _PLAN_OUTPUT_RE.match(tool_output)
    return match.group(1) if match else tool_output


class PlanDialog(Vertical):
    """展示待审批的计划摘要，提供 Accept/Reject 两个按钮。"""

    # 用计划摘要文本初始化对话框
    def __init__(self, plan_summary: str) -> None:
        super().__init__(id="plan-dialog")
        self._plan_summary = plan_summary

    def compose(self):
        yield Static(f"[bold]Plan:[/bold]\n{self._plan_summary}")
        with Vertical():
            yield Button("Accept — exit plan mode", id="plan-accept", variant="success")
            yield Button("Reject — stay in plan mode", id="plan-reject", variant="error")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/unit/test_plan_dialog.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 接入 KamaTuiApp**

在 TUI 的工具完成事件处理逻辑里（`tool.finished` / `ToolCallFinishedEvent` 对应的分支），加判断：

```python
        elif t == "tool.finished" and event.get("tool_name") == "exit_plan_mode":
            from kivi_agent.tui.plan_dialog import PlanDialog, parse_plan_summary
            summary = parse_plan_summary(str(event.get("output", "")))
            self.mount(PlanDialog(summary), before="#prompt")
```

新增按钮点击处理（Textual 的 `on_button_pressed` 事件）：

```python
    # 处理计划对话框的 Accept/Reject 按钮点击
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "plan-accept":
            await self._send_set_permission_mode("default")
            self.query_one(PlanDialog).remove()
        elif event.button.id == "plan-reject":
            self.query_one(PlanDialog).remove()

    # 通过协议命令通知 daemon 切换权限模式
    async def _send_set_permission_mode(self, mode: str) -> None:
        if self._client is not None and self._session_id is not None:
            await self._client.send_command(
                "permission.set_mode", {"session_id": self._session_id, "mode": mode}
            )
```

（若 `KamaTuiApp` 已存在同名的 `on_button_pressed` 方法，把上面的分支合并进去而不是新增重复的事件处理器——Textual 每个消息类型只应该有一个处理入口。）

- [ ] **Step 6: 全量回归**

Run: `uv run pytest tests/unit -v`
Run: `uv run ruff check src tests`
Run: `uv run mypy src`
Expected: 全部通过

- [ ] **Step 7: 提交**

```bash
git add src/kivi_agent/tui/plan_dialog.py src/kivi_agent/tui/app.py tests/unit/test_plan_dialog.py
git commit -m "feat: 新增计划模式对话框，Accept 时通过协议命令切换权限模式"
```

---

## Self-Review Notes

- **覆盖范围**：H1 是前置重构；H2-H3 覆盖 M31（会话恢复，简化为只读展示 + 手动 `--replay`，不做完整交互式选择，见 H3 Step 4 说明）；H4-H5 覆盖 M43（团队树）；H6-H7 覆盖 M41（计划对话框）。M44（断线重连思路）没有单独任务——`_socket_loop()` 现有的重连机制已经覆盖了"断线重连"本身，会话列表界面（H3）让用户看到重连后哪些会话可以继续，这就是 M44 在个人版里的体现方式，不需要额外组件。
- **协议改动的验收标准更严格**：H4、H6 都改了 `core/bus/events.py`/`commands.py`，每处改动后都要求跑 `gen_protocol_doc.py` 并提交 `WIRE_PROTOCOL.md`，这是仓库 `CLAUDE.md` 明确写的规则，Self-Review 时要重点检查这两个任务有没有漏掉这一步。
- **类型一致性**：`TeamTreeState`（H5）消费的事件字段名（`team_id`/`goal`/`members`/`run_id`/`status`）与 H4 定义的 `TeamCreatedEvent` 以及已有的 `SubagentStartedEvent`/`SubagentFinishedEvent` 字段名完全对应，没有出现改名。`format_session_row`（H3）的参数类型 `Session`/`CheckpointData | None` 直接复用包 E/已有的类型定义，未重新定义等价类型。
