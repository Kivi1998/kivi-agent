"""FakeAgentRuntime — in-process kivi-core mock（agent: package-web-e2e-v3）。

WT-E5 用：在 Playwright E2E 启动时把本类注入 FastAPI Gateway 的 ``create_app(runtime=...)``，
gateway 路由层只持有 ``AgentRuntime`` 引用，无法区分真假，所以**真实事件流**经过
``WebSocketBridge`` 推到浏览器（不是浏览器侧 mock）。

事件触发策略（按 goal 模式）：
- 包含 "对比" / "网上" / "知识库" / "RAG" → 多意图链路：
  rag.sources_cited → chart.rendered → llm.thinking(synth) → frontend.tool_call_responded → run.finished
- 包含 "取消" / "stop" / "cancel" → run.cancelled + run.finished
- 其他 → 通用：llm.thinking → run.finished

设计：
- 简单可移植：仅依赖 pydantic + kivi_agent.core.bus；不依赖 anthropic / 任何外部 API
- 完全可预测：事件顺序由 goal 决定，不依赖时间
- 双向：支持 start_session → send_command → subscribe_events 完整链路
- 缓冲重放：每个 subscriber 启动时先收到 buffer 快照，再收未来事件
  （解决"start_session 之后才订阅"导致漏掉 lifecycle 事件的问题）
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from kivi_agent.core.bus.commands import (
    SessionCancelCommand,
    SessionCancelResult,
)
from kivi_agent.core.bus.events import (
    ChartRenderedEvent,
    FrontendToolCallResponded,
    LlmThinkingEvent,
    RagSourcesCitedEvent,
    RunCancelledEvent,
    RunFinishedEvent,
    RunStartedEvent,
    SessionCreatedEvent,
    SessionMessageReceivedEvent,
)
from kivi_agent.core.gateway.runtime import SessionInfo

# ---- 工具 -----------------------------------------------------------

def _now() -> str:
    """ISO 8601 UTC 时间戳字符串。"""
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    """生成带前缀的唯一 ID。"""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


# ---- 配置：goal 模式 → 事件序列 --------------------------------------

# 事件模板：含 type + 其他字段（session_id/run_id/ts 在入队时注入）
# 占位符 {goal_preview} 会替换
_FALLBACK_EVENTS: list[dict[str, Any]] = [
    {
        "type": "session.created",
        "mode": "chat",
    },
    {
        "type": "session.message_received",
        "content": "{goal}",
    },
    {
        "type": "run.started",
        "goal": "{goal}",
    },
    {
        "type": "llm.thinking",
        "step": 0,
        "content": "分析用户问题: {goal_preview}",
    },
    {
        "type": "run.finished",
        "status": "success",
        "reason": None,
        "steps": 1,
    },
]

# 多意图：对比 RAG / 知识库 / 网上
_MULTI_INTENT_EVENTS: list[dict[str, Any]] = [
    {
        "type": "session.created",
        "mode": "chat",
    },
    {
        "type": "session.message_received",
        "content": "{goal}",
    },
    {
        "type": "run.started",
        "goal": "{goal}",
    },
    {
        "type": "rag.sources_cited",
        "sources": [
            {"id": "kb-001", "title": "RAG 架构设计要点", "score": 0.95},
            {"id": "kb-002", "title": "知识库最佳实践", "score": 0.92},
        ],
    },
    {
        "type": "chart.rendered",
        "chart_id": "chart-rag-comparison",
        "option_dict": {
            "title": {"text": "RAG vs 知识库召回率"},
            "xAxis": {"type": "category", "data": ["RAG", "知识库", "混合"]},
            "yAxis": {"type": "value"},
            "series": [
                {"name": "线上", "type": "bar", "data": [85, 60, 92]},
                {"name": "内部", "type": "bar", "data": [70, 95, 88]},
            ],
        },
    },
    {
        "type": "llm.thinking",
        "step": 1,
        "content": "综合 rag + web 检索结果，生成回答...",
    },
    {
        "type": "frontend.tool_call_responded",
        "request_id": "ftcr-1",
        "result": {"displayed": True, "widget": "comparison_table"},
    },
    {
        "type": "run.finished",
        "status": "success",
        "reason": None,
        "steps": 3,
    },
]

# 取消模式
_CANCEL_EVENTS: list[dict[str, Any]] = [
    {
        "type": "session.created",
        "mode": "chat",
    },
    {
        "type": "session.message_received",
        "content": "{goal}",
    },
    {
        "type": "run.started",
        "goal": "{goal}",
    },
    {
        "type": "run.cancelled",
        "reason": "user_requested",
    },
    {
        "type": "run.finished",
        "status": "failed",
        "reason": "cancelled",
        "steps": 0,
    },
]

# 模式定义（按优先级匹配）
@dataclass(frozen=True)
class _PatternSpec:
    """goal 模式匹配规则。"""

    pattern: re.Pattern[str]
    events: list[dict[str, Any]]
    description: str


_PATTERNS: list[_PatternSpec] = [
    _PatternSpec(
        pattern=re.compile(r"取消|stop|cancel", re.IGNORECASE),
        events=_CANCEL_EVENTS,
        description="cancel",
    ),
    _PatternSpec(
        pattern=re.compile(r"多意图|multi|对比.*RAG|网上.*知识库|RAG.*知识库|对比网上", re.IGNORECASE),
        events=_MULTI_INTENT_EVENTS,
        description="multi_intent_rag_web",
    ),
]


# ---- FakeAgentRuntime ------------------------------------------------


@dataclass
class _SessionState:
    """单个 session 的内部状态。

    使用 buffer 模式：所有事件先入 buffer；新 subscriber 先消费 buffer，再消费 live queue。
    这样保证"先 start_session 后 subscribe_events"也能拿到 lifecycle 事件。
    """

    info: SessionInfo
    buffer: list[dict[str, Any]] = field(default_factory=list)
    # 每个 subscriber 一个 condition + cursor；subscriber 等待 buffer 增长时阻塞
    subscribers: list[dict[str, Any]] = field(default_factory=list)
    cancelled: bool = False
    finished: bool = False
    run_id: str | None = None
    event_count: int = 0


class FakeAgentRuntime:
    """Mock kivi-core AgentRuntime（WT-E5 用，Playwright 启动时注入 FastAPI Gateway）。

    与 ``kivi_agent.core.gateway.runtime.AgentRuntime`` Protocol duck-typed 兼容
    （同名同形方法 + 异步生成器）。
    """

    def __init__(self, *, tick_interval: float = 0.0) -> None:
        """参数：
        - tick_interval: 事件之间的延迟（秒），默认 0 即立即推完全部事件。
          E2E 场景下保持 0 即可，避免拖慢 CI；单元测试可调高。
        """
        self._sessions: dict[str, _SessionState] = {}
        self._tick_interval = tick_interval
        # 记录 send_command 调用（单元测试断言用）
        self.commands_sent: list[tuple[str, str]] = []  # (session_id, command_type)

    # ---- AgentRuntime 接口 ------------------------------------------

    async def start_session(self, user_id: str, goal: str) -> SessionInfo:
        """创建并启动 session。同步把 lifecycle + 业务事件入 buffer。"""
        session_id = _new_id("sess")
        run_id = _new_id("run")
        info = SessionInfo(
            session_id=session_id,
            user_id=user_id,
            goal=goal,
            created_at=_now(),
            status="active",
            run_id=run_id,
        )
        state = _SessionState(info=info, run_id=run_id)
        self._sessions[session_id] = state

        # 同步触发 lifecycle + 业务事件（写入 buffer，subscriber 自然消费）
        spec = self._match_pattern(goal)
        for evt_template in spec.events:
            await asyncio.sleep(self._tick_interval)
            evt = self._build_event(evt_template, state, goal)
            await self._append_event(state, evt)

        if not state.cancelled:
            state.finished = True
        return info

    async def cancel_session(self, session_id: str, reason: str) -> bool:
        """取消 session。追加 run.cancelled + run.finished 事件。"""
        state = self._sessions.get(session_id)
        if state is None:
            return False
        if state.finished:
            return False
        state.cancelled = True
        await self._append_event(
            state,
            {
                "type": "run.cancelled",
                "session_id": session_id,
                "run_id": state.run_id,
                "reason": reason or "user_requested",
                "ts": _now(),
            },
        )
        await self._append_event(
            state,
            {
                "type": "run.finished",
                "session_id": session_id,
                "run_id": state.run_id,
                "status": "failed",
                "reason": "cancelled",
                "steps": state.event_count,
                "ts": _now(),
            },
        )
        state.finished = True
        return True

    async def list_sessions(self, user_id: str) -> list[SessionInfo]:
        """列出 user 的所有 session。"""
        return [s.info for s in self._sessions.values() if s.info.user_id == user_id]

    async def get_session(self, session_id: str) -> SessionInfo | None:
        """查询单个 session。"""
        state = self._sessions.get(session_id)
        if state is None:
            return None
        return state.info

    async def send_command(self, session_id: str, command: BaseModel) -> BaseModel:
        """发送命令。"""
        cmd_type = getattr(command, "type", "<unknown>")
        self.commands_sent.append((session_id, str(cmd_type)))

        # 统一处理 SessionCancel
        if isinstance(command, SessionCancelCommand):
            cancelled = await self.cancel_session(session_id, command.reason)
            return SessionCancelResult(
                session_id=session_id,
                cancelled=cancelled,
                ts=_now(),
            )

        # 通用命令：返回 ack
        return _DictResult(data={"ack": True, "session_id": session_id, "type": cmd_type})

    async def subscribe_events(self, session_id: str) -> AsyncIterator[dict[str, Any]]:
        """订阅 session 事件流。

        buffer 模式（重放语义）：
        - subscriber 启动时 cursor=0，先消费 buffer 中所有已存在的事件
        - 然后等 condition 唤醒，消费后续新事件
        - 收到 run.finished 后 drain 完剩余事件再退出
        """
        state = self._sessions.get(session_id)
        if state is None:
            return

        sub: dict[str, Any] = {
            "cursor": 0,  # 起点 = 0；重放 buffer 中所有已有事件
            "event": asyncio.Event(),
            "active": True,
            "stop_after_drain": False,  # 收到 run.finished 后置 True
        }
        state.subscribers.append(sub)
        try:
            while True:
                # drain buffer
                while sub["cursor"] < len(state.buffer):
                    evt = state.buffer[sub["cursor"]]
                    sub["cursor"] += 1
                    yield evt
                    if evt.get("type") == "run.finished":
                        # 收到 run.finished，drain 完剩余事件后退出
                        sub["stop_after_drain"] = True
                # 如果标记了 stop 且已 drain 完，退出
                if sub["stop_after_drain"]:
                    return
                # 等待新事件
                await sub["event"].wait()
                sub["event"].clear()
        finally:
            sub["active"] = False
            try:
                state.subscribers.remove(sub)
            except ValueError:
                pass

    # ---- 内部 helper ------------------------------------------------

    @staticmethod
    def _match_pattern(goal: str) -> _PatternSpec:
        """匹配 goal 对应的模式。fallback 到通用 single-intent。"""
        for spec in _PATTERNS:
            if spec.pattern.search(goal):
                return spec
        # fallback: 单意图
        return _PatternSpec(
            pattern=re.compile(".*"),
            events=_FALLBACK_EVENTS,
            description="fallback_single_intent",
        )

    def _build_event(
        self, template: dict[str, Any], state: _SessionState, goal: str
    ) -> dict[str, Any]:
        """从模板构造事件 dict（注入 session_id/run_id/ts + 替换占位符）。"""
        evt = dict(template)
        evt["session_id"] = state.info.session_id
        evt["run_id"] = state.run_id
        goal_preview = goal[:30] + ("..." if len(goal) > 30 else "")
        for k, v in list(evt.items()):
            if isinstance(v, str):
                if v == "{goal}":
                    evt[k] = goal
                elif v == "{goal_preview}":
                    evt[k] = goal_preview
        if "ts" not in evt:
            evt["ts"] = _now()
        return evt

    async def _append_event(self, state: _SessionState, event: dict[str, Any]) -> None:
        """把事件追加到 buffer 并唤醒所有 subscriber。"""
        # 校验事件类型
        evt_type = event.get("type")
        if evt_type not in _VALID_EVENT_TYPES:
            raise ValueError(f"FakeAgentRuntime 试图推送未知事件类型: {evt_type!r}")
        state.buffer.append(event)
        state.event_count += 1
        # 唤醒所有等待的 subscriber
        for sub in list(state.subscribers):
            if sub["active"]:
                sub["event"].set()

    # ---- 工具方法（测试用）-----------------------------------------

    def get_session_state(self, session_id: str) -> _SessionState | None:
        """获取 session 内部状态（测试断言用）。"""
        return self._sessions.get(session_id)

    def reset(self) -> None:
        """清空所有 session（单元测试 fixture 用）。"""
        self._sessions.clear()
        self.commands_sent.clear()


# ---- 已知事件类型白名单（防止 fake runtime 推错事件）---------------

_VALID_EVENT_TYPES: set[str] = {
    "session.created",
    "session.message_received",
    "session.closed",
    "run.started",
    "run.finished",
    "llm.thinking",
    "rag.sources_cited",
    "chart.rendered",
    "frontend.tool_call_responded",
    "run.cancelled",
}


# ---- 辅助 Pydantic 模型 --------------------------------------------


class _DictResult(BaseModel):
    """通用 Result fallback：把响应 dict 整体打包。"""

    data: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def __contains__(self, key: str) -> bool:
        return key in self.data

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


# ---- Pydantic 事件类型（运行时校验用）------------------------------


# 给单元测试用的便捷导出
__all__ = [
    "FakeAgentRuntime",
    "LlmThinkingEvent",
    "RagSourcesCitedEvent",
    "ChartRenderedEvent",
    "RunCancelledEvent",
    "RunStartedEvent",
    "RunFinishedEvent",
    "SessionCreatedEvent",
    "SessionMessageReceivedEvent",
    "FrontendToolCallResponded",
]
