"""LLM Provider 的 Fake 实现。

为什么不用 `unittest.mock.MagicMock`：
- MagicMock 的副作用是返回 MagicMock 自身，链式 .chat() 返回 MagicMock()，
  后续断言 `result.text == "..."` 会很迷
- 我们的 Fake 是**显式可观察的**（call_count / last_messages / responses 序列）

支持 2 种工作模式：
1. **脚本模式**（推荐）：构造时给一个 `LlmScriptedResponse` 列表，按调用顺序消费
2. **Echo 模式**：未配脚本时，回 echo 用户的最后一条 user message

两者都**支持流式**：FakeLlmProvider 在 chat() 中按 chunk_size 切片发布 LlmTokenEvent。
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from kivi_agent.core.llm.types import LlmResponse, ToolCallBlock, UsageStats


class _BusLike(Protocol):
    """任何有 publish 方法的对象（兼容生产 EventBus 与 FakeEventBus）。"""

    async def publish(self, event: Any) -> None: ...


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class LlmScriptedResponse:
    """单条脚本化 LLM 响应。

    模拟 LLM 返回 + 调用 tool 的最小信息集。
    """

    text: str = ""
    tool_calls: list[ToolCallBlock] = field(default_factory=list)
    stop_reason: str = "end_turn"
    # 用量统计（用于 Judge 修复后端到端验证）
    input_tokens: int = 10
    output_tokens: int = 5
    # 模拟异常（按调用顺序触发）
    raise_exc: BaseException | None = None
    # 流式切片大小（模拟 token-by-token 推送）
    chunk_size: int = 1


class FakeLlmProvider:
    """LLMProvider 协议的离线实现。

    实现要点：
    - 100% 离线，不调用任何外部 API
    - 支持 `tool_schemas` 参数但**不真实**校验 JSON Schema
    - 通过 `bus.publish(LlmTokenEvent(...))` 模拟流式输出
    - 通过 `scripted` 列表按顺序消费响应；耗尽后回退到 echo 模式
    """

    def __init__(
        self,
        scripted: Iterable[LlmScriptedResponse] | None = None,
        *,
        model: str = "fake-model",
    ) -> None:
        self._scripted: list[LlmScriptedResponse] = list(scripted or [])
        self._call_index = 0
        self._model = model
        # 观测字段（测试用）
        self.call_count: int = 0
        self.last_messages: list[dict[str, object]] = []
        self.last_tool_schemas: list[dict[str, object]] = []
        self.last_run_id: str | None = None
        self.last_step: int | None = None
        # 触发过的所有 token 切片（仅 chunk_size=1 时与 text 等长）
        self.published_tokens: list[str] = []

    # 重置所有观测状态（不改变 scripted 列表）
    def reset(self) -> None:
        self._call_index = 0
        self.call_count = 0
        self.last_messages = []
        self.last_tool_schemas = []
        self.last_run_id = None
        self.last_step = None
        self.published_tokens = []

    # LLMProvider 协议入口：流式返回 + 逐 token 发布事件
    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: _BusLike,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        # 观测：记录调用上下文
        self.call_count += 1
        self.last_messages = list(messages)
        self.last_tool_schemas = list(tool_schemas)
        self.last_run_id = run_id
        self.last_step = step

        # 选响应：脚本优先，否则 echo
        if self._call_index < len(self._scripted):
            resp_def = self._scripted[self._call_index]
            self._call_index += 1
        else:
            # echo 模式：最后一条 user 消息
            user_text = ""
            for m in reversed(messages):
                role = m.get("role")
                if role == "user":
                    content = m.get("content")
                    user_text = content if isinstance(content, str) else ""
                    break
            resp_def = LlmScriptedResponse(text=f"[echo] {user_text}", stop_reason="end_turn")

        # 模拟异常（仅在生产 fake chat 抛出，未进入流式循环）
        if resp_def.raise_exc is not None:
            raise resp_def.raise_exc

        # 流式发布 LlmTokenEvent
        text = resp_def.text
        chunk_size = max(1, resp_def.chunk_size)
        for i in range(0, len(text), chunk_size):
            chunk = text[i : i + chunk_size]
            self.published_tokens.append(chunk)
            await bus.publish(
                _make_token_event(run_id=run_id, token=chunk, ts=_now_iso())
            )

        # 流式结束即构造 LlmResponse
        return LlmResponse(
            stop_reason=resp_def.stop_reason,
            tool_calls=list(resp_def.tool_calls),
            text=text,
            usage=UsageStats(
                input_tokens=resp_def.input_tokens,
                output_tokens=resp_def.output_tokens,
            ),
        )

    # 辅助构造：模拟"先 text 再 tool_call"的两段式响应
    @classmethod
    def with_tool_call(
        cls,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        text_prefix: str = "I'll check that.",
    ) -> FakeLlmProvider:
        scripted = [
            LlmScriptedResponse(
                text=text_prefix,
                tool_calls=[
                    ToolCallBlock(
                        id="call_1",
                        name=tool_name,
                        input=tool_input,
                    )
                ],
                stop_reason="tool_use",
            ),
            LlmScriptedResponse(
                text="Done.",
                stop_reason="end_turn",
            ),
        ]
        return cls(scripted=scripted)


# 导入 Pydantic 事件类型（避免在 __init__ 顶部导入，让 _fakes.llm 也可独立 import）
def _make_token_event(run_id: str, token: str, ts: str) -> Any:
    from kivi_agent.core.bus.events import LlmTokenEvent

    return LlmTokenEvent(run_id=run_id, token=token, ts=ts)
