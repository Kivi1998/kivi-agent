from __future__ import annotations

import asyncio
from typing import Any

from kama_claude.core.tools.builtin.ask_user import AskUserTool, QuestionStore


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
