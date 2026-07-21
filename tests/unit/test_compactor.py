from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from kama_claude.core.compact.compactor import Compactor
from kama_claude.core.context import ExecutionContext
from kama_claude.core.events.bus import EventBus
from kama_claude.core.llm.types import LlmResponse, UsageStats


def _stub_provider(summary: str = "## 1. Original Goal\nTest\n## 2. Completed Steps\n- done") -> Any:
    provider = MagicMock()
    provider.chat = AsyncMock(return_value=LlmResponse(
        stop_reason="end_turn",
        text=summary,
        usage=UsageStats(input_tokens=100, output_tokens=30),
    ))
    return provider


def _make_messages(n: int = 5) -> list[dict[str, Any]]:
    msgs = []
    for i in range(n):
        msgs.append({"role": "user", "content": "user message " + "x" * 200})
        msgs.append({"role": "assistant", "content": "assistant reply " + "y" * 200})
    return msgs


# 功能：验证 compact_messages 成功时 provider.chat 被调用一次且不传工具 schema
# 设计：stub provider 返回非空摘要，断言 chat 调用一次，tool_schemas=[]
def test_compact_messages_calls_provider(tmp_path: Path) -> None:
    provider = _stub_provider()
    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "sess-1")
    messages = _make_messages()

    result = asyncio.get_event_loop().run_until_complete(
        compactor.compact_messages(messages, provider)
    )

    assert result is not None
    provider.chat.assert_called_once()
    call_kwargs = provider.chat.call_args
    assert call_kwargs.kwargs.get("tool_schemas") == [] or call_kwargs.args[1] == []


# 功能：验证 compact_messages 返回的摘要文本来自 provider 响应
# 设计：stub provider 返回固定摘要字符串，断言 result.summary_text 等于该字符串
def test_compact_messages_returns_summary(tmp_path: Path) -> None:
    expected = "## 1. Original Goal\nDo X\n## 2. Completed\n- step one"
    provider = _stub_provider(summary=expected)
    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "sess-1")

    result = asyncio.get_event_loop().run_until_complete(
        compactor.compact_messages(_make_messages(), provider)
    )

    assert result is not None
    assert result.summary_text == expected


# 功能：验证 compact() 将 context.messages 替换为两条摘要消息对
# 设计：调用 compact() 后断言 messages 长度为 2，role 分别为 user/assistant
def test_compact_replaces_context_messages(tmp_path: Path) -> None:
    provider = _stub_provider()
    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "sess-1")
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    ctx.messages = _make_messages()

    asyncio.get_event_loop().run_until_complete(compactor.compact(ctx, provider))

    assert len(ctx.messages) == 2
    assert ctx.messages[0]["role"] == "user"
    assert ctx.messages[1]["role"] == "assistant"


# 功能：验证 compact() 在 session 目录写入 summary_*.md 文件
# 设计：使用 tmp_path，调用 compact() 后检查目录内是否存在 summary_ 开头的文件
def test_compact_writes_summary_file(tmp_path: Path) -> None:
    provider = _stub_provider()
    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "sess-1")
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    ctx.messages = _make_messages()

    asyncio.get_event_loop().run_until_complete(compactor.compact(ctx, provider))

    summary_files = list(tmp_path.glob("summary_*.md"))
    assert len(summary_files) == 1


# 功能：验证 compact() 成功后发布 ContextCompactedEvent 事件
# 设计：订阅 EventBus，收集事件，断言收到类型为 context.compacted 的事件
def test_compact_publishes_event(tmp_path: Path) -> None:
    provider = _stub_provider()
    bus = EventBus()
    received: list[Any] = []

    async def handler(event: Any) -> None:
        received.append(event)

    bus.subscribe(handler)
    compactor = Compactor(bus, tmp_path, "sess-1")
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    ctx.messages = _make_messages()

    asyncio.get_event_loop().run_until_complete(compactor.compact(ctx, provider))

    types = [getattr(e, "type", None) for e in received]
    assert "context.compacted" in types


# 功能：验证 provider 抛异常时 context.messages 保持不变
# 设计：stub provider.chat 抛 RuntimeError，断言 compact() 返回 None 且 messages 未被修改
def test_compact_failure_preserves_context(tmp_path: Path) -> None:
    provider = MagicMock()
    provider.chat = AsyncMock(side_effect=RuntimeError("LLM error"))
    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "sess-1")
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    original_messages = _make_messages()
    ctx.messages = list(original_messages)

    result = asyncio.get_event_loop().run_until_complete(compactor.compact(ctx, provider))

    assert result is None
    assert ctx.messages == original_messages


# 功能：验证连续 3 次压缩失败（LLM 返回空摘要）后 is_circuit_open() 变为 True
# 设计：用返回空文本的假 provider 连续调用 compact_messages 3 次，
#      断言前 2 次 is_circuit_open() 仍为 False（未达阈值），第 3 次之后变 True，
#      覆盖"阈值触发"这个边界而不是随便断言个大概
async def test_circuit_opens_after_three_consecutive_failures(tmp_path: Path) -> None:
    from kama_claude.core.compact.compactor import Compactor
    from kama_claude.core.events.bus import EventBus

    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "s1")
    fake_provider = AsyncMock()
    fake_provider.chat.return_value.text = ""
    fake_provider.chat.return_value.usage = None

    for _ in range(2):
        await compactor.compact_messages([{"role": "user", "content": "x"}], fake_provider)
        assert compactor.is_circuit_open() is False

    await compactor.compact_messages([{"role": "user", "content": "x"}], fake_provider)
    assert compactor.is_circuit_open() is True


# 功能：验证一次成功压缩会把连续失败计数清零，重新打开熔断
# 设计：先制造 2 次失败（未达阈值），再来一次成功，断言 consecutive_failures 归零
async def test_success_resets_failure_count(tmp_path: Path) -> None:
    from kama_claude.core.compact.compactor import Compactor
    from kama_claude.core.events.bus import EventBus

    bus = EventBus()
    compactor = Compactor(bus, tmp_path, "s1")
    fake_provider = AsyncMock()

    fake_provider.chat.return_value.text = ""
    fake_provider.chat.return_value.usage = None
    await compactor.compact_messages([{"role": "user", "content": "x"}], fake_provider)
    await compactor.compact_messages([{"role": "user", "content": "x"}], fake_provider)
    assert compactor.consecutive_failures == 2

    fake_provider.chat.return_value.text = "a good summary"
    fake_provider.chat.return_value.usage = MagicMock(output_tokens=5)
    await compactor.compact_messages([{"role": "user", "content": "x"}], fake_provider)
    assert compactor.consecutive_failures == 0


# 功能：验证 compact() 在熔断打开时直接跳过、不调用 provider，且发布 CompactionSkippedEvent
# 设计：先制造 3 次失败让熔断打开，然后调用 compact() 并断言 provider.chat 未被调用、收到 skipped 事件
async def test_compact_short_circuits_when_open_and_publishes_skipped(tmp_path: Path) -> None:
    from kama_claude.core.bus.events import CompactionSkippedEvent
    from kama_claude.core.compact.compactor import Compactor
    from kama_claude.core.events.bus import EventBus

    bus = EventBus()
    received: list[Any] = []

    async def handler(event: Any) -> None:
        received.append(event)

    bus.subscribe(handler)
    compactor = Compactor(bus, tmp_path, "sess-1")
    fake_provider = AsyncMock()
    fake_provider.chat.return_value.text = ""
    fake_provider.chat.return_value.usage = None

    for _ in range(3):
        await compactor.compact_messages([{"role": "user", "content": "x"}], fake_provider)
    assert compactor.is_circuit_open() is True

    fake_provider.chat.reset_mock()
    ctx = ExecutionContext(run_id="r1", goal="test", max_steps=5)
    ctx.messages = _make_messages()
    result = await compactor.compact(ctx, fake_provider)
    assert result is None
    fake_provider.chat.assert_not_called()
    types = [getattr(e, "type", None) for e in received]
    assert "compaction.skipped" in types
    skipped = next(e for e in received if isinstance(e, CompactionSkippedEvent))
    assert skipped.reason == "circuit_open"
