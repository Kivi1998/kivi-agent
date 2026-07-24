from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx
import pytest

from kivi_agent.core.llm.errors import (
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from kivi_agent.core.llm.provider import (
    AnthropicProvider,
    CompletionResult,
    StreamChunk,
    TokenUsage,
)

# --- helpers --------------------------------------------------------------


def _text_block(text: str) -> MagicMock:
    # 功能：构造一个 anthropic text content block 的 mock
    b = MagicMock()
    b.type = "text"
    b.text = text
    return b


def _tool_use_block(tool_id: str, name: str, input_obj: dict[str, Any]) -> MagicMock:
    # 功能：构造一个 anthropic tool_use content block 的 mock
    b = MagicMock()
    b.type = "tool_use"
    b.id = tool_id
    b.name = name
    b.input = input_obj
    return b


def _make_response(
    blocks: list[MagicMock] | None = None,
    stop_reason: str = "end_turn",
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> MagicMock:
    # 功能：构造 anthropic Message 的 mock，含 content / usage / stop_reason / model
    msg = MagicMock()
    msg.content = blocks or []
    msg.stop_reason = stop_reason
    msg.model = model
    msg.usage = MagicMock(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    return msg


def _make_client_with_response(response: MagicMock) -> MagicMock:
    # 功能：构造一个 mock anthropic 客户端（client.messages.create 异步返回给定 response）
    client = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


def _make_client_with_side_effect(excs: list[BaseException], final: MagicMock) -> MagicMock:
    # 功能：构造一个先抛若干异常再成功的 mock 客户端（用于重试测试）
    client = MagicMock()
    side: list[Any] = list(excs) + [final]
    client.messages.create = AsyncMock(side_effect=side)
    return client


def _rate_limit_error(message: str = "rate limited") -> anthropic.RateLimitError:
    # 功能：构造一个 429 RateLimitError
    resp = httpx.Response(429, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    return anthropic.RateLimitError(message, response=resp, body=None)


def _internal_error(status: int = 500) -> anthropic.InternalServerError:
    # 功能：构造一个 5xx InternalServerError
    resp = httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    return anthropic.InternalServerError(f"status {status}", response=resp, body=None)


def _bad_request_error(status: int = 400) -> anthropic.BadRequestError:
    # 功能：构造一个 4xx BadRequestError（不可重试）
    resp = httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    return anthropic.BadRequestError(f"status {status}", response=resp, body=None)


class _FakeStream:
    # 功能：模拟 anthropic messages.stream() 返回的异步上下文管理器
    def __init__(self, texts: list[str], final: MagicMock) -> None:
        self._texts = texts
        self._final = final

    async def __aenter__(self) -> _FakeStream:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass

    @property
    def text_stream(self) -> Any:
        async def _gen() -> Any:
            for t in self._texts:
                yield t

        return _gen()

    async def get_final_message(self) -> MagicMock:
        return self._final


# --- TokenUsage dataclass -------------------------------------------------


# 功能：验证 TokenUsage.total_tokens 等于 input + output
def test_token_usage_total_property() -> None:
    u = TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15)
    assert u.total_tokens == 15


# 功能：验证零 token 时 total 也为零
def test_token_usage_total_zero() -> None:
    u = TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0)
    assert u.total_tokens == 0


# --- 构造 -----------------------------------------------------------------


# 功能：验证显式 api_key + base_url 时不读 env，直接构造 AsyncAnthropic
def test_constructor_with_explicit_api_key_and_base_url() -> None:
    with patch("kivi_agent.core.llm.provider.anthropic.AsyncAnthropic") as mock_cls:
        provider = AnthropicProvider(
            model="claude-sonnet-4-6",
            api_key="sk-ant-explicit",
            base_url="https://api.deepseek.com/anthropic",
            timeout=15.0,
            max_retries=2,
            temperature=0.3,
            max_tokens=2048,
        )
    mock_cls.assert_called_once_with(
        api_key="sk-ant-explicit",
        base_url="https://api.deepseek.com/anthropic",
    )
    assert provider._timeout == 15.0
    assert provider._max_retries == 2
    assert provider._temperature == 0.3
    assert provider._max_tokens == 2048


# 功能：验证未传 client / api_key / env 时抛 SystemExit（保留 Wave 1 行为）
def test_constructor_missing_api_key_system_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit):
        AnthropicProvider(model="any")


# 功能：验证显式 client 注入时跳过 API key 检查
def test_constructor_client_injection_skips_key() -> None:
    client = MagicMock()
    provider = AnthropicProvider(model="m", client=client)
    assert provider._client is client


# --- complete() 基础 ------------------------------------------------------


# 功能：验证 complete() 返回 CompletionResult，content / usage / model 字段正确
async def test_complete_basic_text_response() -> None:
    response = _make_response(blocks=[_text_block("Hello")])
    client = _make_client_with_response(response)
    provider = AnthropicProvider(model="claude-sonnet-4-6", client=client)
    result = await provider.complete(messages=[{"role": "user", "content": "hi"}])
    assert isinstance(result, CompletionResult)
    assert result.content == "Hello"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5
    assert result.usage.total_tokens == 15
    assert result.model == "claude-sonnet-4-6"
    assert result.stop_reason == "end_turn"
    assert result.tool_calls == []


# 功能：验证 complete() 多 text block 拼接为完整 content
async def test_complete_concatenates_multiple_text_blocks() -> None:
    response = _make_response(blocks=[_text_block("foo"), _text_block("bar")])
    client = _make_client_with_response(response)
    provider = AnthropicProvider(model="m", client=client)
    result = await provider.complete(messages=[{"role": "user", "content": "x"}])
    assert result.content == "foobar"


# 功能：验证 complete() 解析 tool_use block 为 tool_calls 列表
async def test_complete_with_tool_use() -> None:
    tool_block = _tool_use_block(
        "toolu_01", "read_file", {"path": "README.md"}
    )
    response = _make_response(blocks=[tool_block], stop_reason="tool_use")
    client = _make_client_with_response(response)
    provider = AnthropicProvider(model="m", client=client)
    result = await provider.complete(
        messages=[{"role": "user", "content": "read readme"}]
    )
    assert result.stop_reason == "tool_use"
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert tc.id == "toolu_01"
    assert tc.name == "read_file"
    assert tc.arguments == {"path": "README.md"}


# 功能：验证 complete() 把 model / max_tokens / temperature 透传给 client
async def test_complete_passes_model_and_params() -> None:
    response = _make_response()
    client = _make_client_with_response(response)
    provider = AnthropicProvider(
        model="claude-opus-4-6",
        client=client,
        temperature=0.2,
        max_tokens=1024,
    )
    await provider.complete(messages=[{"role": "user", "content": "x"}])
    kwargs = client.messages.create.await_args.kwargs
    assert kwargs["model"] == "claude-opus-4-6"
    assert kwargs["max_tokens"] == 1024
    assert kwargs["temperature"] == 0.2
    assert kwargs["messages"] == [{"role": "user", "content": "x"}]


# 功能：验证 complete() 在有 tools 时把 tools 透传给 client
async def test_complete_passes_tools() -> None:
    response = _make_response(blocks=[_tool_use_block("id1", "fn", {})])
    client = _make_client_with_response(response)
    provider = AnthropicProvider(model="m", client=client)
    tools = [
        {
            "name": "fn",
            "description": "do fn",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]
    await provider.complete(messages=[{"role": "user", "content": "x"}], tools=tools)
    kwargs = client.messages.create.await_args.kwargs
    assert kwargs["tools"] == tools


# --- complete() 重试 ------------------------------------------------------


# 功能：验证 429 错误触发指数退避重试（1s / 2s / 4s），第二次成功
async def test_complete_retries_on_429_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final = _make_response(blocks=[_text_block("ok")])
    client = _make_client_with_side_effect(
        [_rate_limit_error(), _rate_limit_error()], final
    )
    provider = AnthropicProvider(model="m", client=client, max_retries=3)
    sleeps: list[float] = []
    # 功能：monkeypatch 替换 provider 模块内的 asyncio.sleep 记录退避秒数
    async def _fake_sleep(s: float) -> None:
        sleeps.append(s)
    monkeypatch.setattr("kivi_agent.core.llm.provider.asyncio.sleep", _fake_sleep)
    result = await provider.complete(messages=[{"role": "user", "content": "x"}])
    assert result.content == "ok"
    assert sleeps == [1.0, 2.0]
    assert client.messages.create.await_count == 3


# 功能：验证 500 错误触发指数退避重试
async def test_complete_retries_on_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final = _make_response(blocks=[_text_block("recovered")])
    client = _make_client_with_side_effect(
        [_internal_error(500)], final
    )
    provider = AnthropicProvider(model="m", client=client, max_retries=2)
    async def _fake_sleep(s: float) -> None:
        return None
    monkeypatch.setattr("kivi_agent.core.llm.provider.asyncio.sleep", _fake_sleep)
    result = await provider.complete(messages=[{"role": "user", "content": "x"}])
    assert result.content == "recovered"
    assert client.messages.create.await_count == 2


# 功能：验证 503 错误也触发重试
async def test_complete_retries_on_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final = _make_response(blocks=[_text_block("recovered")])
    client = _make_client_with_side_effect([_internal_error(503)], final)
    provider = AnthropicProvider(model="m", client=client, max_retries=2)
    monkeypatch.setattr(
        "kivi_agent.core.llm.provider.asyncio.sleep",
        AsyncMock(),
    )
    result = await provider.complete(messages=[{"role": "user", "content": "x"}])
    assert result.content == "recovered"
    assert client.messages.create.await_count == 2


# 功能：验证重试耗尽后抛出 LLMRateLimitError（429 永不成功）
async def test_complete_raises_rate_limit_after_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client_with_side_effect(
        [_rate_limit_error() for _ in range(4)], _make_response()
    )
    provider = AnthropicProvider(model="m", client=client, max_retries=3)
    monkeypatch.setattr(
        "kivi_agent.core.llm.provider.asyncio.sleep",
        AsyncMock(),
    )
    with pytest.raises(LLMRateLimitError):
        await provider.complete(messages=[{"role": "user", "content": "x"}])
    assert client.messages.create.await_count == 4  # 1 initial + 3 retries


# 功能：验证重试耗尽后抛出 LLMUnavailableError（5xx 永不成功）
async def test_complete_raises_unavailable_after_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client_with_side_effect(
        [_internal_error(503) for _ in range(4)], _make_response()
    )
    provider = AnthropicProvider(model="m", client=client, max_retries=2)
    monkeypatch.setattr(
        "kivi_agent.core.llm.provider.asyncio.sleep",
        AsyncMock(),
    )
    with pytest.raises(LLMUnavailableError):
        await provider.complete(messages=[{"role": "user", "content": "x"}])


# 功能：验证 4xx 错误（不可重试）立即抛出，不消耗重试预算
async def test_complete_no_retry_on_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client_with_side_effect([_bad_request_error(400)], _make_response())
    provider = AnthropicProvider(model="m", client=client, max_retries=3)
    sleep_mock = AsyncMock()
    monkeypatch.setattr(
        "kivi_agent.core.llm.provider.asyncio.sleep", sleep_mock
    )
    with pytest.raises(LLMError):
        await provider.complete(messages=[{"role": "user", "content": "x"}])
    assert client.messages.create.await_count == 1
    sleep_mock.assert_not_called()


# --- complete() 超时 ------------------------------------------------------


# 功能：验证 client 调用超过 timeout 时抛 LLMTimeoutError，不重试
async def test_complete_timeout_raises_llm_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()

    async def _slow(**_kwargs: Any) -> Any:
        await asyncio.sleep(0.5)
        return _make_response()

    client.messages.create = _slow
    provider = AnthropicProvider(
        model="m", client=client, timeout=0.05, max_retries=0
    )
    with pytest.raises(LLMTimeoutError):
        await provider.complete(messages=[{"role": "user", "content": "x"}])


# --- 错误归一化 -----------------------------------------------------------


# 功能：验证 anthropic RateLimitError 归一化为 LLMRateLimitError
async def test_rate_limit_error_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client_with_side_effect(
        [_rate_limit_error("quota")], _make_response()
    )
    provider = AnthropicProvider(model="m", client=client, max_retries=0)
    monkeypatch.setattr(
        "kivi_agent.core.llm.provider.asyncio.sleep",
        AsyncMock(),
    )
    with pytest.raises(LLMRateLimitError) as ei:
        await provider.complete(messages=[{"role": "user", "content": "x"}])
    assert "quota" in str(ei.value)


# 功能：验证 anthropic 5xx 归一化为 LLMUnavailableError
async def test_unavailable_error_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _make_client_with_side_effect(
        [_internal_error(503)], _make_response()
    )
    provider = AnthropicProvider(model="m", client=client, max_retries=0)
    monkeypatch.setattr(
        "kivi_agent.core.llm.provider.asyncio.sleep",
        AsyncMock(),
    )
    with pytest.raises(LLMUnavailableError):
        await provider.complete(messages=[{"role": "user", "content": "x"}])


# 功能：验证 anthropic APITimeoutError 归一化为 LLMTimeoutError
async def test_api_timeout_error_normalized() -> None:
    client = MagicMock()
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    client.messages.create = AsyncMock(
        side_effect=anthropic.APITimeoutError(request=request)
    )
    provider = AnthropicProvider(model="m", client=client, max_retries=0)
    with pytest.raises(LLMTimeoutError):
        await provider.complete(messages=[{"role": "user", "content": "x"}])


# --- stream_complete() ----------------------------------------------------


# 功能：验证 stream_complete() 按顺序 yield 每个 text delta 的 StreamChunk
async def test_stream_complete_yields_text_chunks_in_order() -> None:
    final = _make_response(input_tokens=20, output_tokens=7)
    client = MagicMock()
    client.messages.stream = MagicMock(
        return_value=_FakeStream(["He", "llo", "!"], final)
    )
    provider = AnthropicProvider(model="m", client=client)
    chunks: list[StreamChunk] = []
    async for c in provider.stream_complete(
        messages=[{"role": "user", "content": "x"}]
    ):
        chunks.append(c)
    assert [c.content for c in chunks] == ["He", "llo", "!", ""]
    assert all(c.usage is None for c in chunks[:-1])


# 功能：验证 stream_complete() 最后一个 chunk 携带 usage 且 finish_reason=stop
async def test_stream_complete_final_chunk_has_usage_and_done() -> None:
    final = _make_response(input_tokens=42, output_tokens=11)
    client = MagicMock()
    client.messages.stream = MagicMock(return_value=_FakeStream(["ok"], final))
    provider = AnthropicProvider(model="m", client=client)
    chunks: list[StreamChunk] = []
    async for c in provider.stream_complete(
        messages=[{"role": "user", "content": "x"}]
    ):
        chunks.append(c)
    last = chunks[-1]
    assert last.finish_reason == "stop"
    assert last.usage is not None
    assert last.usage.input_tokens == 42
    assert last.usage.output_tokens == 11


# 功能：验证 stream_complete() 空流时只 yield 终态 chunk
async def test_stream_complete_empty_text_yields_only_final() -> None:
    final = _make_response(input_tokens=1, output_tokens=0)
    client = MagicMock()
    client.messages.stream = MagicMock(return_value=_FakeStream([], final))
    provider = AnthropicProvider(model="m", client=client)
    chunks: list[StreamChunk] = []
    async for c in provider.stream_complete(
        messages=[{"role": "user", "content": "x"}]
    ):
        chunks.append(c)
    assert len(chunks) == 1
    assert chunks[0].finish_reason == "stop"
    assert chunks[0].content == ""


# 功能：验证 stream_complete() 在第一次 429 后重试，第二次成功
async def test_stream_complete_retries_on_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final = _make_response(blocks=[_text_block("recovered")], input_tokens=2, output_tokens=1)
    client = MagicMock()
    # 功能：第一次 stream 抛 RateLimitError，第二次成功
    call_count = {"n": 0}

    def _stream_factory(**_kwargs: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise _rate_limit_error()
        return _FakeStream(["recovered"], final)

    client.messages.stream = MagicMock(side_effect=_stream_factory)
    provider = AnthropicProvider(model="m", client=client, max_retries=2)
    monkeypatch.setattr(
        "kivi_agent.core.llm.provider.asyncio.sleep",
        AsyncMock(),
    )
    chunks: list[StreamChunk] = []
    async for c in provider.stream_complete(
        messages=[{"role": "user", "content": "x"}]
    ):
        chunks.append(c)
    assert "".join(c.content for c in chunks[:-1]) == "recovered"
    assert chunks[-1].finish_reason == "stop"
    assert call_count["n"] == 2


# 功能：验证 stream_complete() 重试耗尽后抛 LLMRateLimitError
async def test_stream_complete_raises_after_max_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    client.messages.stream = MagicMock(side_effect=_rate_limit_error())
    provider = AnthropicProvider(model="m", client=client, max_retries=2)
    monkeypatch.setattr(
        "kivi_agent.core.llm.provider.asyncio.sleep",
        AsyncMock(),
    )
    with pytest.raises(LLMRateLimitError):
        async for _ in provider.stream_complete(
            messages=[{"role": "user", "content": "x"}]
        ):
            pass
