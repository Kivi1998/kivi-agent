from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from kama_claude.core.events.bus import EventBus
from kama_claude.core.llm.types import LlmResponse, UsageStats
from kama_claude.core.subagent.registry import BackgroundTaskRegistry
from kama_claude.core.subagent.tool import spawn_background_subagent


# 功能：验证 spawn_background_subagent 直接返回 run_id 字符串，而不是包一层 ToolResult 文本
# 设计：这是 Task F4 TeamManager 复用这个函数的前提——需要能直接拿到 run_id 编程使用，
#      不应该依赖解析"...run_id=xxx..."这种自然语言格式
async def test_spawn_background_subagent_returns_run_id(tmp_path: Path) -> None:
    fake_provider = AsyncMock()
    fake_provider.chat = AsyncMock(
        return_value=LlmResponse(
            stop_reason="end_turn",
            tool_calls=[],
            text="done",
            usage=UsageStats(0, 0, 0, 0, 0.0),
        )
    )

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
