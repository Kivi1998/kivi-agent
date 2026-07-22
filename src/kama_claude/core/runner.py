from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kama_claude.core.bus.events import (
    AskUserRequestedEvent,
    RunFinishedEvent,
    RunStartedEvent,
)
from kama_claude.core.compact.compactor import Compactor
from kama_claude.core.config import KamaConfig
from kama_claude.core.context import ExecutionContext
from kama_claude.core.events.bus import EventBus, EventHandler
from kama_claude.core.events.writer import EventWriter
from kama_claude.core.filehistory.history import FileHistory
from kama_claude.core.hooks.engine import HookEngine
from kama_claude.core.hooks.loader import load_hooks
from kama_claude.core.llm.base import LLMProvider
from kama_claude.core.llm.factory import build_provider
from kama_claude.core.loop import AgentLoop
from kama_claude.core.mcp.server import McpServerManager
from kama_claude.core.memory.loader import load_context_file
from kama_claude.core.memory.recall import build_memory_prompt
from kama_claude.core.memory.store import MemoryStore
from kama_claude.core.permissions.manager import PermissionManager
from kama_claude.core.runs import RUNS_DIR, new_run_id
from kama_claude.core.session.checkpoint import CheckpointData, CheckpointStore
from kama_claude.core.session.model import Session
from kama_claude.core.session.store import SessionStore
from kama_claude.core.subagent.registry import BackgroundTaskRegistry
from kama_claude.core.subagent.tool import AgentResultTool, SpawnAgentTool
from kama_claude.core.task.manager import TaskManager
from kama_claude.core.tools.builtin import (
    AskUserTool,
    BashTool,
    EditFileTool,
    ExitPlanModeTool,
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
from kama_claude.core.tools.builtin.ask_user import QuestionStore
from kama_claude.core.tools.file_state_cache import FileStateCache
from kama_claude.core.tools.registry import ToolRegistry
from kama_claude.core.trace.provider import TracingProvider
from kama_claude.core.trace.writer import TraceWriter


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class RunOutcome:
    status: str
    result: str
    reason: str | None


class AgentRunner:
    # 组装所有运行时依赖，准备执行一次完整的 agent run
    def __init__(
        self,
        config: KamaConfig,
        *,
        bus: EventBus | None = None,
        provider: LLMProvider | None = None,
        extra_handlers: list[EventHandler] | None = None,
        runs_dir: Path | None = None,
        trace: TraceWriter | None = None,
        permission_manager: PermissionManager | None = None,
        question_store: QuestionStore | None = None,
        mcp_manager: McpServerManager | None = None,
    ) -> None:
        self._config = config
        self._bus = bus
        self._provider = provider
        self._extra_handlers: list[EventHandler] = extra_handlers or []
        self._runs_dir = runs_dir or RUNS_DIR
        self._trace = trace
        self._permission_manager = permission_manager
        self._mcp_manager = mcp_manager
        # 跨 run 共享的 ask_user 问题挂起注册表（所有 ask_user 工具共用同一份，
        # 这样 spawn_agent 子 run 也能复用主 run 的 TUI 弹窗通道）
        self._question_store = question_store or QuestionStore()
        # file_state_cache（agent: package-c）：read_file 写、edit_file 读，
        # 检测"读后改"过期。每 run 一份即可，不需要跨 run 持久化。
        self._file_state_cache = FileStateCache()
        # file_history（agent: package-c）—— 存放在 <project>/.kama/file-history/
        self._file_history = FileHistory(Path.cwd() / ".kama" / "file-history")
        # 跨 run 共享的后台 subagent 任务注册表
        self._task_registry = BackgroundTaskRegistry()
        # package-f: 团队管理器，跨 _build_registry() 调用持久化，使同一 run 内后续
        # team_status/team_message 能查到之前 team_create 创建的团队
        # provider/bus 在 _build_registry() 阶段按当前 run 重新绑定（见 _bind_team_manager）
        from kama_claude.core.events.bus import EventBus as _EventBus
        from kama_claude.core.teams.manager import TeamManager
        self._team_manager = TeamManager(
            provider=provider,
            bus=bus or _EventBus(),
            permission_manager=permission_manager,
            max_steps=self._config.agent.max_steps,
            task_registry=self._task_registry,
            runs_dir=self._runs_dir,
            session_id="",
        )
        # 钩子引擎：从配置加载的钩子在工具调用前后执行
        self._hook_engine = HookEngine(load_hooks(self._config.hooks))

    # 构建工具注册表，注入 TaskManager（任务工具共享同一实例）；可选注入 SpawnAgentTool
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
        allowed: set[str] | None = set(tool_whitelist) if tool_whitelist else None

        def _ok(name: str) -> bool:
            return allowed is None or name in allowed

        registry = ToolRegistry()
        for t in [
            ReadFileTool(self._file_state_cache),
            WriteFileTool(),
            ListDirTool(),
        ]:
            if _ok(t.name):
                registry.register(t)
        # tool_search（agent: package-b）：在构建完基础工具后注册，让它能引用同一 registry 做关键词搜索
        if _ok("tool_search"):
            from kama_claude.core.tools.builtin.tool_search import ToolSearchTool
            registry.register(ToolSearchTool(registry))
        # bash（agent: minimal-loop）: 构造时注入平台沙箱（macOS Seatbelt / Linux bwrap），不允许网络
        from kama_claude.core.sandbox import create_sandbox
        bash_tool = BashTool(sandbox=create_sandbox(), allow_write=[str(child_runs_dir)])
        if _ok(bash_tool.name):
            registry.register(bash_tool)
        # glob（agent: minimal-loop）
        from kama_claude.core.tools.builtin.glob_tool import GlobTool
        glob_tool = GlobTool()
        if _ok(glob_tool.name):
            registry.register(glob_tool)
        # grep（agent: minimal-loop）
        from kama_claude.core.tools.builtin.grep_tool import GrepTool
        grep_tool = GrepTool()
        if _ok(grep_tool.name):
            registry.register(grep_tool)
        # edit_file（agent: package-c 增强 staleness）：与 ReadFileTool 共享同一份 cache
        edit_file_tool = EditFileTool(self._file_state_cache)
        if _ok(edit_file_tool.name):
            registry.register(edit_file_tool)
        # diff（agent: minimal-loop）
        from kama_claude.core.tools.builtin.diff_tool import DiffTool
        diff_tool = DiffTool()
        if _ok(diff_tool.name):
            registry.register(diff_tool)
        # enter_worktree（agent: minimal-loop）
        from kama_claude.core.tools.builtin.enter_worktree import EnterWorktreeTool
        enter_worktree_tool = EnterWorktreeTool()
        if _ok(enter_worktree_tool.name):
            registry.register(enter_worktree_tool)
        # exit_worktree（agent: minimal-loop）
        from kama_claude.core.tools.builtin.exit_worktree import ExitWorktreeTool
        exit_worktree_tool = ExitWorktreeTool()
        if _ok(exit_worktree_tool.name):
            registry.register(exit_worktree_tool)
        # exit_plan_mode（agent: package-d）
        if _ok("exit_plan_mode"):
            registry.register(ExitPlanModeTool())
        for t in [
            TaskCreateTool(task_manager),
            TaskUpdateTool(task_manager),
            TaskListTool(task_manager),
            TaskGetTool(task_manager),
        ]:
            if _ok(t.name):
                registry.register(t)
        if session is not None and store is not None and run_id is not None:
            note_tool = NoteSaveTool(store, session.id, run_id)
            if _ok(note_tool.name):
                registry.register(note_tool)
        if provider is not None and bus is not None and run_id is not None:
            runs_dir = child_runs_dir or self._runs_dir
            if _ok("spawn_agent"):
                registry.register(
                    SpawnAgentTool(
                        provider=provider,
                        parent_bus=bus,
                        parent_run_id=run_id,
                        permission_manager=self._permission_manager,
                        max_steps=self._config.agent.max_steps,
                        task_registry=self._task_registry,
                        runs_dir=runs_dir,
                        session_id=session_id,
                        depth=0,
                    )
                )
            if _ok("agent_result"):
                registry.register(AgentResultTool(self._task_registry))
            # team_create（agent: package-f）：复用跨 _build_registry() 调用的 self._team_manager
            if _ok("team_create"):
                from kama_claude.core.tools.builtin.team_create import TeamCreateTool
                registry.register(TeamCreateTool(self._team_manager))
            # team_message（agent: package-f）：mailbox 写到 per-session 的 runs 目录
            if _ok("team_message"):
                from kama_claude.core.tools.builtin.team_message import TeamMessageTool
                mailbox_root = child_runs_dir or self._runs_dir
                registry.register(TeamMessageTool(mailbox_root=mailbox_root))
            # team_status（agent: package-f）：只读状态查询，复用 team_manager
            if _ok("team_status"):
                from kama_claude.core.tools.builtin.team_status import TeamStatusTool
                registry.register(TeamStatusTool(self._team_manager))
        if self._mcp_manager is not None:
            for mcp_tool in self._mcp_manager.get_tools():
                if _ok(mcp_tool.name):
                    registry.register(mcp_tool)
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
        # rewind_file（agent: package-c）
        if _ok("rewind_file"):
            registry.register(RewindFileTool(self._file_history))
        return registry

    # 执行一次完整的 agent run（委托给 run_and_capture，忽略返回值）
    async def run(self, goal: str, *, run_id: str | None = None) -> None:
        await self.run_and_capture(goal, run_id=run_id)

    # 执行 agent run 并返回 RunOutcome（含最终文字结果）
    async def run_and_capture(
        self,
        goal: str,
        *,
        run_id: str | None = None,
        session: Session | None = None,
        store: SessionStore | None = None,
        system_prompt_override: str | None = None,
        tool_whitelist: list[str] | None = None,
    ) -> RunOutcome:
        run_id = run_id or new_run_id()
        if session is not None and store is not None:
            run_path = store.runs_dir(session.id) / run_id
            history = store.read_messages(session.id)
            notes = store.read_notes(session.id)
        else:
            run_path = self._runs_dir / run_id
            history = [{"role": "user", "content": goal}]
            notes = ""
        run_path.mkdir(parents=True, exist_ok=True)

        global_ctx = load_context_file(Path("~/.kama/context.md").expanduser())
        project_ctx = load_context_file(Path(".kama/context.md"))

        task_manager = TaskManager(run_path / ".tasks")

        bus = self._bus if self._bus is not None else EventBus()
        for h in self._extra_handlers:
            bus.subscribe(h)

        # package-e: 跨 session 长期记忆装配点（agent: package-e）——
        # 从 ~/.kama/memory 读取所有记忆条目并渲染成可注入的 system prompt 片段
        memory_store = MemoryStore(Path("~/.kama/memory").expanduser())
        long_term_memory = build_memory_prompt(memory_store)

        context = ExecutionContext(
            run_id=run_id,
            goal=goal,
            max_steps=self._config.agent.max_steps,
            prefill_messages=history,
            session_notes=notes,
            global_context=global_ctx,
            project_context=project_ctx,
            long_term_memory=long_term_memory,
            system_prompt_override=system_prompt_override,
        )
        prefill_len = len(history)

        async with EventWriter(run_path / "events.jsonl") as writer:
            writer.subscribe(bus)
            await bus.publish(RunStartedEvent(run_id=run_id, goal=goal, ts=_now()))

            cancelled = False
            try:
                provider: LLMProvider = self._provider or build_provider(self._config)
                if self._trace is not None:
                    provider = TracingProvider(
                        provider,
                        self._trace,
                        include_payload=self._config.trace.include_llm_payload,
                    )
                session_id_str = session.id if session is not None else ""
                # package-f: 把当前 run 的 provider/bus/session_id 绑到 TeamManager，
                # 使 team_create 工具调用能找到正确的 LLM 后端
                self._team_manager.bind(provider=provider, bus=bus, session_id=session_id_str)
                child_runs_dir = (
                    store.runs_dir(session.id)
                    if session is not None and store is not None
                    else self._runs_dir
                )
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
                # 把当前 registry 的工具分类注入 permission_manager，供 PermissionMode 覆盖用
                if self._permission_manager is not None:
                    self._permission_manager.set_tool_categories(
                        {t.name: t.category for t in registry._tools.values()}
                    )
                session_dir = (
                    store.session_dir(session.id)
                    if session is not None and store is not None
                    else run_path
                )
                compactor = Compactor(bus, session_dir, session_id_str)
                # package-e: 运行检查点装配点（agent: package-e）—— 复用 SessionStore 的根目录
                # 每个 run 的 checkpoint.json 写到 <root>/<sid>/runs/<run_id>/checkpoint.json
                checkpoint_store: CheckpointStore | None = None
                if session is not None and store is not None:
                    checkpoint_store = CheckpointStore(store.session_dir(session.id).parent)
                loop = AgentLoop(
                    provider, registry, bus,
                    permission_manager=self._permission_manager,
                    compactor=compactor,
                    compact_threshold=self._config.compaction.auto_threshold,
                    session_id=session_id_str,
                    hook_engine=self._hook_engine,
                    checkpoint_store=checkpoint_store,
                )
                await loop.run(context)
            except asyncio.CancelledError:
                cancelled = True
                if not context.is_done():
                    context.mark_failed("cancelled")
            except Exception:
                logging.getLogger(__name__).exception(
                    "agent run failed run_id=%s step=%d", run_id, context.step
                )
                if not context.is_done():
                    context.mark_failed("llm_error")

            await bus.publish(
                RunFinishedEvent(
                    run_id=run_id,
                    status=context.status,
                    reason=context.reason,
                    steps=context.step,
                    ts=_now(),
                )
            )

            # package-e: 异步抽取长期记忆（agent: package-e）——
            # fire-and-forget；extract_memories 内部已 try/except 兜底，不影响主流程返回
            from kama_claude.core.memory.extractor import extract_memories
            asyncio.ensure_future(extract_memories(context.messages, provider, memory_store))

        if session is not None and store is not None:
            store.append_messages(session.id, context.messages[prefill_len:], run_id=run_id)

        if cancelled:
            raise asyncio.CancelledError()

        return RunOutcome(
            status=context.status,
            result=context.result,
            reason=context.reason,
        )
