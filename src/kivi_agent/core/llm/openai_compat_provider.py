from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from openai import AsyncOpenAI

from kivi_agent.core.bus.events import LlmModelSelectedEvent, LlmTokenEvent, LlmUsageEvent
from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.llm.catalog import context_window_for
from kivi_agent.core.llm.streaming import StreamAccumulator
from kivi_agent.core.llm.types import LlmResponse, UsageStats


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


# 把 Anthropic 风格的工具 schema（name/description/input_schema）转换成 OpenAI function-calling 格式
def _convert_tool_schema(tool: dict[str, object]) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


class OpenAICompatProvider:
    # 初始化 OpenAI 兼容客户端；client 可在测试时注入以跳过真实网络请求
    def __init__(self, model: str, *, base_url: str, api_key: str, client: Any = None) -> None:
        self._model = model
        self._client: Any = client or AsyncOpenAI(base_url=base_url, api_key=api_key)

    # 流式调用 OpenAI 兼容 Chat Completions API，聚合增量为完整 LlmResponse
    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: EventBus,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        await bus.publish(
            LlmModelSelectedEvent(run_id=run_id, model=self._model, strategy="static", ts=_now())
        )

        openai_messages: list[dict[str, object]] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        openai_messages.extend(messages)

        kwargs: dict[str, object] = {
            "model": self._model,
            "messages": openai_messages,
            "stream": True,
        }
        if tool_schemas:
            kwargs["tools"] = [_convert_tool_schema(t) for t in tool_schemas]

        stream = await self._client.chat.completions.create(**kwargs)

        acc = StreamAccumulator()
        usage: Any = None

        async for chunk in stream:
            choice = chunk.choices[0]
            delta = choice.delta
            if delta is None:
                continue
            if delta.content:
                acc.add_content_delta(delta.content)
                await bus.publish(LlmTokenEvent(run_id=run_id, token=delta.content, ts=_now()))
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    acc.add_tool_call_delta(
                        tc.index, tc.id or "", tc.function.name or "", tc.function.arguments or ""
                    )
            if choice.finish_reason:
                usage = chunk.usage

        text, tool_calls = acc.finalize()

        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        context_pct = input_tokens / context_window_for(self._model)

        await bus.publish(
            LlmUsageEvent(
                run_id=run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                context_pct=context_pct,
                ts=_now(),
            )
        )

        return LlmResponse(
            stop_reason="tool_use" if tool_calls else "end_turn",
            tool_calls=tool_calls,
            text=text,
            usage=UsageStats(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                context_pct=context_pct,
            ),
        )
