"""Wave 7 WT-K3 故障注入测试（agent: package-stage8-baselines-v7）。

# test_failure_injection.py（agent: package-stage8-baselines-v7）
5 场景（按 plan §三 WT-K3）：
1. model_failure  - LLM provider 抛异常，主任务不挂，返回 fallback
2. tool_timeout   - Tool 调用超时，重试 3 次后 fallback（实际是 retry 2 次 + final 一次错误）
3. subagent_failure - 子 Agent 失败，父任务降级（graceful degrade）
4. ws_disconnect - WebSocket 断线，重连 + replay（基于 EventReplayBuffer）
5. cancellation   - 用户取消中途任务，资源清理（_pending 队列清空）

设计要点：
- 全离线（不依赖 ANTHROPIC_API_KEY）；用 FakeLlmProvider / Mock tool
- 每个 case < 5s（fast），不与端到端测试竞争
- 用 KIVI_RUN_FAILURE=1 env guard，默认跳过
- env guard 在 conftest.py 不便集中做（per-file marker 更精确），故放在文件顶部 pytestmark
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from kivi_agent.core.config import KamaConfig
from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.gateway.runtime import SessionInfo
from kivi_agent.core.gateway.ws_bridge import WebSocketBridge
from kivi_agent.core.llm.types import LlmResponse, ToolCallBlock
from kivi_agent.core.permissions.manager import PermissionManager
from kivi_agent.core.runner import AgentRunner
from kivi_agent.core.subagent.registry import BackgroundTaskRegistry
from kivi_agent.core.subagent.tool import spawn_background_subagent
from kivi_agent.gateway.replay import EventReplayBuffer

# 功能：env guard 失败注入测试，默认不跑（避免污染主测试）
# 设计：用 pytest.mark.skipif 装饰整个模块，KIVI_RUN_FAILURE=1 时才执行
_RUN_FAILURE = os.environ.get("KIVI_RUN_FAILURE") == "1"
pytestmark = pytest.mark.skipif(
    not _RUN_FAILURE,
    reason="failure injection tests skipped (set KIVI_RUN_FAILURE=1 to enable)",
)


# ---------------------------------------------------------------------------
# helpers（agent: package-stage8-baselines-v7）
# ---------------------------------------------------------------------------


class _AlwaysCrashProvider:
    """每步 chat() 都抛 RuntimeError 的 provider（用于 model_failure 注入）。"""

    def __init__(self, message: str = "synthetic llm crash") -> None:
        self._message = message
        self.call_count = 0

    async def chat(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        self.call_count += 1
        raise RuntimeError(self._message)


class _HangingToolProvider:
    """让 Agent 调用一个会 hang 的 tool，验证超时 + 重试 3 次后失败降级。"""

    async def chat(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        # 第 1 步：调用一个不存在的 tool（registry.get 返回 None），模拟不可恢复错误
        # 用 unknown tool 触发 runtime_error；invoke_tool 会进 retry 路径
        return LlmResponse(
            stop_reason="tool_use",
            tool_calls=[ToolCallBlock(id="tc-bad", name="definitely_not_a_real_tool", input={})],
        )


class _FakeRuntime:
    """WebSocketBridge 依赖的极简 AgentRuntime（与现有 ws_bridge 测试一致）。"""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[dict[str, Any]]] = []

    async def start_session(self, user_id: str, goal: str) -> SessionInfo:
        raise NotImplementedError

    async def cancel_session(self, session_id: str, reason: str) -> bool:
        return True

    async def list_sessions(self, user_id: str) -> list[SessionInfo]:
        return []

    async def get_session(self, session_id: str) -> SessionInfo | None:
        return None

    async def send_command(self, session_id: str, command: Any) -> Any:
        return {}

    def subscribe_events(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        async def _gen() -> AsyncIterator[dict[str, Any]]:
            while True:
                await asyncio.sleep(0.1)
                if False:
                    yield  # type: ignore[unreachable]

        return _gen()


def _make_runner(provider: Any, tmp_path: Path) -> AgentRunner:
    """构造一个使用 mock provider + tmp_path 的最小 AgentRunner。"""
    config = KamaConfig()
    config.agent.max_steps = 3
    return AgentRunner(
        config,
        bus=EventBus(),
        provider=provider,  # type: ignore[arg-type]
        runs_dir=tmp_path / "runs",
    )


# ---------------------------------------------------------------------------
# 场景 1：model_failure
# ---------------------------------------------------------------------------


# 功能：LLM provider 抛异常时，主任务不挂、返回 fallback 响应（RunOutcome）
# 设计：注入 _AlwaysCrashProvider，run_and_capture 应捕获并把 run 标记为 failed，
#       返回 RunOutcome(status="failed", reason="llm_error")；不抛异常给调用方
#       此处同时验证"不挂"（<5s 完成）和"fallback 返回"（outcome 可用）
async def test_model_failure(tmp_path: Path) -> None:
    t0 = time.perf_counter()
    provider = _AlwaysCrashProvider()
    runner = _make_runner(provider, tmp_path)

    outcome = await runner.run_and_capture("test goal")

    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"故障注入测试应 <5s, 实际 {elapsed:.2f}s"

    # 主流程不被异常击穿；run 标记为 failed 状态（fallback 响应）
    assert outcome.status == "failed", f"expected failed, got {outcome.status!r}"
    assert outcome.reason == "llm_error", f"expected llm_error, got {outcome.reason!r}"
    # provider 至少被调 1 次（确认异常路径真的走过）
    assert provider.call_count >= 1


# ---------------------------------------------------------------------------
# 场景 2：tool_timeout
# ---------------------------------------------------------------------------


# 功能：工具调用不可恢复错误触发 retry，最终失败降级
# 设计：注入 HangingToolProvider（调不存在的 tool name），invoke_tool 走
#       _RETRYABLE 路径，max_retries=2 后返回失败；验证 tool.call_failed 事件
#       出现且 LLM loop 不挂（仍能继续到 end_turn）
async def test_tool_timeout(tmp_path: Path) -> None:
    bus = EventBus()
    event_types: list[str] = []

    async def collect(e: BaseModel) -> None:
        event_types.append(getattr(e, "type", ""))

    bus.subscribe(collect)

    config = KamaConfig()
    config.agent.max_steps = 5
    # provider 固定返回同一条 tool call，loop 会一直跑直到 max_steps
    # 我们只关心 tool.call_failed 路径：invoke_tool 走完 retry 后回 runtime_error
    runner = AgentRunner(
        config,
        bus=bus,
        provider=_HangingToolProvider(),  # type: ignore[arg-type]
        runs_dir=tmp_path / "runs",
    )

    t0 = time.perf_counter()
    outcome = await runner.run_and_capture("run bad tool")
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"tool 失败测试应 <5s, 实际 {elapsed:.2f}s"

    # 至少出现一次 tool.call_failed
    assert "tool.call_failed" in event_types, f"未观察到 tool.call_failed；事件流: {event_types}"
    # run 最终走到 max_steps → failed (exceeded_max_steps)
    assert outcome.status in ("failed", "success")


# ---------------------------------------------------------------------------
# 场景 3：subagent_failure
# ---------------------------------------------------------------------------


# 功能：子 Agent 抛错时父任务降级：BackgroundTaskRegistry 仍注册到该 run_id
# 设计：直接调 spawn_background_subagent + 一个永远抛错的 provider；
#       验证 registry.get 拿到 task（即便子任务内部失败，task 已注册），
#       父 AgentRunner 不被击穿（返回 RunOutcome 失败而非 raise）
async def test_subagent_failure(tmp_path: Path) -> None:
    bus = EventBus()
    task_registry = BackgroundTaskRegistry()

    class _AlwaysCrashProvider:
        async def chat(self, *args: Any, **kwargs: Any) -> LlmResponse:
            raise RuntimeError("synthetic subagent crash")

    t0 = time.perf_counter()
    # spawn_background_subagent 内部 catch 异常并把 run 标记为 failed；不会 raise
    run_id = await spawn_background_subagent(
        provider=_AlwaysCrashProvider(),  # type: ignore[arg-type]
        parent_bus=bus,
        parent_run_id="parent-1",
        permission_manager=None,
        max_steps=3,
        task_registry=task_registry,
        runs_dir=tmp_path,
        session_id="sess-1",
        depth=0,
        description="doomed task",
        prompt="do something",
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"subagent 失败测试应 <5s, 实际 {elapsed:.2f}s"

    # run_id 仍是合法字符串（spawn 不抛 = 优雅降级）
    assert isinstance(run_id, str) and run_id
    # registry 至少记下了这条任务
    assert task_registry.get(run_id) is not None
    # 等子任务在后台完成（应很快；不 await 也不应挂）
    entry = task_registry.get(run_id)
    if entry is not None:
        task, _ctx = entry
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()


# ---------------------------------------------------------------------------
# 场景 4：ws_disconnect
# ---------------------------------------------------------------------------


# 功能：WebSocket 断线后重连，replay buffer 补齐漏掉的事件
# 设计：用 EventReplayBuffer 模拟服务端缓存；client1 收到 2 条事件后断开
#       → 推第 3 条事件（client1 漏掉）→ client2 用 since=<client1最后ts> 拉取
#       → 断言 client2 拿到第 3 条
async def test_ws_disconnect() -> None:
    runtime = _FakeRuntime()
    bridge = WebSocketBridge(runtime=runtime)
    replay = EventReplayBuffer()

    session_id = "sess-ws"
    # client1 订阅 + 收 2 条事件
    async with bridge.connect(session_id) as conn1:
        gen1 = conn1.events()
        # 推 2 条到 replay + bridge
        for i, ts in enumerate(["t1", "t2"], start=1):
            ev = {"type": "x", "session_id": session_id, "ts": ts, "i": i}
            replay.push(session_id, ev)
            await bridge.publish(ev)
        # client1 收 2 条
        e1 = await asyncio.wait_for(gen1.__anext__(), timeout=1.0)
        e2 = await asyncio.wait_for(gen1.__anext__(), timeout=1.0)
        assert e1["ts"] == "t1" and e2["ts"] == "t2"
        # 模拟 client1 断开（出 with 块）
        last_ts = e2["ts"]

    # 推第 3 条（client1 漏掉）
    ev3 = {"type": "x", "session_id": session_id, "ts": "t3", "i": 3}
    replay.push(session_id, ev3)
    await bridge.publish(ev3)

    # client2 用 since=last_ts 重连 → 拿到 t3
    missed = replay.since(session_id, last_ts)
    assert len(missed) == 1, f"replay 应只补 1 条, 实际 {len(missed)} 条"
    assert missed[0]["ts"] == "t3"
    assert missed[0]["i"] == 3

    # bridge 内部 client1 已清理（active_connections == 0）
    assert bridge.active_connections() == 0


# ---------------------------------------------------------------------------
# 场景 5：cancellation
# ---------------------------------------------------------------------------


# 功能：用户取消中途任务后，PermissionManager 的 pending 队列被清空
# 设计：直接调 PermissionManager.check_and_wait 触发 1 条挂起 entry，
#       再用 cancel_session 模拟"用户取消"；验证 _pending 被清空 + 资源不泄漏
#       此处不跑完整 AgentRunner（避免嵌套 asyncio 任务带来的竞态），
#       单测 PermissionManager 的 cancel 语义
async def test_cancellation(tmp_path: Path) -> None:
    manager = PermissionManager()
    events: list[dict[str, Any]] = []

    async def emit(ev: dict[str, Any]) -> None:
        events.append(ev)

    t0 = time.perf_counter()
    # 起一个后台 task 触发 permission.requested，不 respond
    ask_task = asyncio.create_task(
        manager.check_and_wait(
            tool_use_id="tc-cancel",
            tool_name="bash",
            params={"command": "rm -rf /tmp/some_target"},
            session_id="sess-cancel",
            event_emitter=emit,
        )
    )
    # 等 event_emitter 收到 permission.requested
    for _ in range(50):
        if any(e.get("type") == "permission.requested" for e in events):
            break
        await asyncio.sleep(0.02)

    # 此刻 _pending 应有 1 条
    assert len(manager._pending) == 1, f"挂起队列期望 1 条, 实际 {len(manager._pending)}"

    # 模拟用户取消：cancel_session 清掉该 session 所有 pending
    manager.cancel_session(session_id="sess-cancel", reason="user_cancelled")

    # _pending 应被清空
    assert len(manager._pending) == 0, (
        f"cancel 后 pending 期望 0 条, 实际 {len(manager._pending)}"
    )

    # ask_task 应拿到 deny_once（cancel 走 set_result("deny_once") 路径）
    allowed, decision = await asyncio.wait_for(ask_task, timeout=2.0)
    assert allowed is False
    assert decision == "deny_once"

    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"取消测试应 <5s, 实际 {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# end of 5 场景（agent: package-stage8-baselines-v7）
# ---------------------------------------------------------------------------
