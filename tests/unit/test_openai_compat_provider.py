from __future__ import annotations

from types import SimpleNamespace

from kama_claude.core.events.bus import EventBus
from kama_claude.core.llm.openai_compat_provider import OpenAICompatProvider


class _FakeStreamChunk:
    def __init__(self, delta_content: str | None = None, tool_call: dict[str, object] | None = None,
                 finish_reason: str | None = None) -> None:
        delta = SimpleNamespace(content=delta_content, tool_calls=None)
        if tool_call is not None:
            delta.tool_calls = [SimpleNamespace(
                index=0,
                id=tool_call["id"],
                function=SimpleNamespace(name=tool_call["name"], arguments=tool_call["arguments"]),
            )]
        self.choices = [SimpleNamespace(delta=delta, finish_reason=finish_reason)]
        self.usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5) if finish_reason else None


class _FakeStream:
    def __init__(self, chunks: list[_FakeStreamChunk]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> _FakeStream:
        return self

    async def __anext__(self) -> _FakeStreamChunk:
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class _FakeCompletions:
    def __init__(self, chunks: list[_FakeStreamChunk]) -> None:
        self._chunks = chunks

    async def create(self, **kwargs: object) -> _FakeStream:
        return _FakeStream(list(self._chunks))


class _FakeChat:
    def __init__(self, chunks: list[_FakeStreamChunk]) -> None:
        self.completions = _FakeCompletions(chunks)


class _FakeOpenAIClient:
    def __init__(self, chunks: list[_FakeStreamChunk]) -> None:
        self.chat = _FakeChat(chunks)


# 功能：验证纯文本回复（无工具调用）能正确聚合成 LlmResponse.text 且 stop_reason 为 end_turn
# 设计：模拟 OpenAI 流式返回两个文本增量 chunk + 一个 finish_reason="stop" chunk，断言拼接结果和用量统计
async def test_chat_aggregates_text_response() -> None:
    chunks = [
        _FakeStreamChunk(delta_content="hel"),
        _FakeStreamChunk(delta_content="lo"),
        _FakeStreamChunk(finish_reason="stop"),
    ]
    provider = OpenAICompatProvider(
        model="test-model", base_url="http://fake", api_key="x",
        client=_FakeOpenAIClient(chunks),
    )
    bus = EventBus()
    response = await provider.chat([], [], bus, run_id="r1")
    assert response.text == "hello"
    assert response.stop_reason == "end_turn"
    assert response.usage is not None
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 5


# 功能：验证工具调用流式返回能正确解析成 ToolCallBlock 且 stop_reason 为 tool_use
# 设计：模拟一个 finish_reason="tool_calls" 的 chunk 携带函数名和参数，断言 tool_calls 列表内容
async def test_chat_parses_tool_call() -> None:
    chunks = [
        _FakeStreamChunk(tool_call={"id": "call_1", "name": "bash", "arguments": '{"command": "ls"}'}),
        _FakeStreamChunk(finish_reason="tool_calls"),
    ]
    provider = OpenAICompatProvider(
        model="test-model", base_url="http://fake", api_key="x",
        client=_FakeOpenAIClient(chunks),
    )
    bus = EventBus()
    response = await provider.chat([], [], bus, run_id="r1")
    assert response.stop_reason == "tool_use"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "bash"
    assert response.tool_calls[0].input == {"command": "ls"}
