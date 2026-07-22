from __future__ import annotations

import asyncio
import itertools
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.tools.base import BaseTool, ToolResult

# 事件 payload 形状：
# {"type": "ask_user.requested", "request_id": str, "question": str, "options": list[str]}
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


# ask_user 工具：在长时间任务中途挂起 LLM，弹出问题等用户回答后继续
class AskUserTool(BaseTool):
    params_model = AskUserParams
    name = "ask_user"
    category = "command"  # 会向用户发起询问（决策/确认类操作），非纯只读也非文件写
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
