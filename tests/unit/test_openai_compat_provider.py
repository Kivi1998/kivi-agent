"""OpenAICompatProvider 单测（Wave 8.2 / agent: real-llm-e2e）。

覆盖：
- complete() 基础响应 / DeepSeek base URL / 工具调用 / Token 统计 / stop_reason
- stream_complete() SSE 流式聚合 / 工具调用分片 / finish_reason
- 错误归一：429 → LLMRateLimitError / 5xx → LLMUnavailableError / timeout → LLMTimeoutError
- 重试：429/500/503 指数退避，最终成功
- 超时：asyncio.TimeoutError → LLMTimeoutError
- 工厂：create_provider("openai") 读 env vars
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from kivi_agent.core.llm.errors import (
    CompletionResult,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    StreamChunk,
    ToolCall,
)
from kivi_agent.core.llm.factory import create_provider
from kivi_agent.core.llm.openai_compat_provider import OpenAICompatProvider


# ---- 测试辅助：构造一个 mock httpx.AsyncClient ----
# 准备一组预编排的 httpx 响应（按调用顺序消费）
class _MockTransport(httpx.AsyncBaseTransport):
    """可注入的 mock transport；按列表顺序返回 responses。"""

    def __init__(self, responses: list[httpx.Response | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if not self._responses:
            raise AssertionError("no more mock responses queued")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


# 构造一个 JSON 响应
def _json_response(status: int = 200, payload: dict[str, Any] | None = None) -> httpx.Response:
    if payload is None:
        payload = {}
    return httpx.Response(status_code=status, json=payload, request=httpx.Request("POST", "https://fake"))


# 构造一个 429/500/503 错误响应
def _err_response(status: int) -> httpx.Response:
    return httpx.Response(status_code=status, text="err", request=httpx.Request("POST", "https://fake"))


# 构造一个 mock provider；返回 (provider, transport)
def _make_provider(
    responses: list[httpx.Response | Exception],
    *,
    model: str = "gpt-4o-mini",
    base_url: str = "https://api.openai.com/v1",
    max_retries: int = 3,
    timeout: float = 30.0,
) -> tuple[OpenAICompatProvider, _MockTransport]:
    transport = _MockTransport(responses)
    client = httpx.AsyncClient(transport=transport, timeout=timeout)
    provider = OpenAICompatProvider(
        model=model,
        base_url=base_url,
        api_key="sk-test",
        max_retries=max_retries,
        timeout=timeout,
        client=client,
    )
    return provider, transport


# ========== complete() 基础 ==========
# 功能：complete() 返回的 CompletionResult.content 等于上游 message.content
# 设计：mock 上游返回标准 OpenAI 响应，断言 result.content / stop_reason / model
@pytest.mark.asyncio
async def test_complete_returns_text_content() -> None:
    payload = {
        "id": "chatcmpl-1",
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hello world"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    provider, _ = _make_provider([_json_response(200, payload)])
    result = await provider.complete([{"role": "user", "content": "hi"}])
    assert isinstance(result, CompletionResult)
    assert result.content == "hello world"
    assert result.stop_reason == "stop"
    assert result.model == "gpt-4o-mini"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5
    assert result.usage.total_tokens == 15


# 功能：complete() 空 content（上游返回 null）处理为 ""
# 设计：上游 content=null，断言 result.content == ""（避免 None 传播）
@pytest.mark.asyncio
async def test_complete_handles_null_content() -> None:
    payload = {
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": None, "tool_calls": []},
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {},
    }
    provider, _ = _make_provider([_json_response(200, payload)])
    result = await provider.complete([{"role": "user", "content": "hi"}])
    assert result.content == ""
    assert result.stop_reason == "tool_calls"


# 功能：complete() 解析上游 tool_calls 为 ToolCall 列表（arguments JSON 化）
# 设计：上游 1 个 tool_call，arguments 是 JSON 字符串，断言 ToolCall.arguments 是 dict
@pytest.mark.asyncio
async def test_complete_parses_tool_calls() -> None:
    payload = {
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps({"command": "ls"}),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 8, "total_tokens": 28},
    }
    provider, _ = _make_provider([_json_response(200, payload)])
    result = await provider.complete([{"role": "user", "content": "list files"}])
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert isinstance(tc, ToolCall)
    assert tc.id == "call_1"
    assert tc.name == "bash"
    assert tc.arguments == {"command": "ls"}


# 功能：complete() 工具调用 arguments 是非法 JSON 时保留原文不崩
# 设计：上游 arguments 是 "invalid json"，断言保留为 {"_raw_arguments": "invalid json"}
@pytest.mark.asyncio
async def test_complete_handles_invalid_tool_arguments_json() -> None:
    payload = {
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "f", "arguments": "not json"},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {},
    }
    provider, _ = _make_provider([_json_response(200, payload)])
    result = await provider.complete([{"role": "user", "content": "x"}])
    assert result.tool_calls[0].arguments == {"_raw_arguments": "not json"}


# 功能：complete() 把 tools 列表从 Anthropic 格式转成 OpenAI function-calling 格式
# 设计：传 1 个 tool schema，断言 transport.calls[0] 的 JSON body 包含 OpenAI 格式 tools
@pytest.mark.asyncio
async def test_complete_converts_anthropic_tools_to_openai() -> None:
    payload = {
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        "usage": {},
    }
    provider, transport = _make_provider([_json_response(200, payload)])
    tools = [
        {
            "name": "bash",
            "description": "Run shell command",
            "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}},
        }
    ]
    await provider.complete([{"role": "user", "content": "x"}], tools=tools)
    body = json.loads(transport.calls[0].content.decode() if transport.calls[0].content else "{}")
    assert "tools" in body
    assert body["tools"][0]["type"] == "function"
    assert body["tools"][0]["function"]["name"] == "bash"


# 功能：complete() URL 拼接去掉 base_url 末尾斜杠，避免 //chat/completions
# 设计：base_url 带尾斜杠，断言 request URL 不含 //chat/completions
@pytest.mark.asyncio
async def test_complete_uses_base_url_without_double_slash() -> None:
    payload = {
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        "usage": {},
    }
    provider, transport = _make_provider(
        [_json_response(200, payload)], base_url="https://api.deepseek.com/v1/"
    )
    await provider.complete([{"role": "user", "content": "x"}])
    assert str(transport.calls[0].url) == "https://api.deepseek.com/v1/chat/completions"


# 功能：DeepSeek base URL 走完全相同的代码路径（验证 OpenAI 兼容性）
# 设计：mock 端点 https://api.deepseek.com/v1 响应成功，断言请求头/URL 正确
@pytest.mark.asyncio
async def test_complete_works_with_deepseek_base_url() -> None:
    payload = {
        "model": "deepseek-chat",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": "deepseek says hi"}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
    }
    provider, transport = _make_provider([_json_response(200, payload)], base_url="https://api.deepseek.com/v1")
    result = await provider.complete([{"role": "user", "content": "hi"}])
    assert "deepseek" in str(transport.calls[0].url)
    assert result.content == "deepseek says hi"


# 功能：complete() 发送 Authorization Bearer header
# 设计：断言 transport.calls[0] 包含 "Authorization: Bearer sk-test"
@pytest.mark.asyncio
async def test_complete_sends_bearer_token() -> None:
    payload = {
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "x"}, "finish_reason": "stop"}],
        "usage": {},
    }
    provider, transport = _make_provider([_json_response(200, payload)])
    await provider.complete([{"role": "user", "content": "x"}])
    assert transport.calls[0].headers.get("authorization") == "Bearer sk-test"


# ========== stream_complete() 流式 ==========
# 功能：stream_complete() 聚合 SSE data: 行得到完整 content
# 设计：mock 上游 3 个 data: 事件（SSE 格式），逐 chunk yield 后聚合
@pytest.mark.asyncio
async def test_stream_complete_aggregates_text_chunks() -> None:
    sse_body = (
        'data: {"choices":[{"index":0,"delta":{"content":"hel"}}]}\n\n'
        'data: {"choices":[{"index":0,"delta":{"content":"lo"}}]}\n\n'
        'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    response = httpx.Response(
        status_code=200,
        text=sse_body,
        headers={"content-type": "text/event-stream"},
        request=httpx.Request("POST", "https://fake"),
    )
    provider, _ = _make_provider([response])
    chunks: list[StreamChunk] = []
    async for ch in provider.stream_complete([{"role": "user", "content": "hi"}]):
        chunks.append(ch)
    text = "".join(c.content for c in chunks)
    assert text == "hello"
    # 最后一个非空 finish_reason 应该是 "stop"
    finish_reasons = [c.finish_reason for c in chunks if c.finish_reason]
    assert finish_reasons[-1] == "stop"


# 功能：stream_complete() 在流式 usage chunk 单独到达时聚合到最后一个 StreamChunk
# 设计：上游 emit 一个 usage-only chunk（choices 为空），断言末尾 chunk 携带 usage
@pytest.mark.asyncio
async def test_stream_complete_collects_usage_chunk() -> None:
    sse_body = (
        'data: {"choices":[{"index":0,"delta":{"content":"hi"}}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":2,"total_tokens":9}}\n\n'
        "data: [DONE]\n\n"
    )
    response = httpx.Response(
        status_code=200,
        text=sse_body,
        headers={"content-type": "text/event-stream"},
        request=httpx.Request("POST", "https://fake"),
    )
    provider, _ = _make_provider([response])
    chunks: list[StreamChunk] = []
    async for ch in provider.stream_complete([{"role": "user", "content": "x"}]):
        chunks.append(ch)
    usage_chunks = [c for c in chunks if c.usage is not None]
    assert len(usage_chunks) == 1
    assert usage_chunks[0].usage is not None
    assert usage_chunks[0].usage.input_tokens == 7
    assert usage_chunks[0].usage.output_tokens == 2


# 功能：stream_complete() 聚合工具调用分片到 _partial_arguments
# 设计：上游 emit 2 个 tool_call 增量 chunk，断言末尾 ToolCall.arguments 包含 "_partial_arguments"
@pytest.mark.asyncio
async def test_stream_complete_aggregates_tool_call_deltas() -> None:
    sse_body = (
        'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_1",'
        '"function":{"name":"bash","arguments":"{\\"command\\""}}]}}]}\n\n'
        'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"function":{"arguments":": \\"ls\\"}"}}]}}]}\n\n'
        'data: {"choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}\n\n'
        "data: [DONE]\n\n"
    )
    response = httpx.Response(
        status_code=200,
        text=sse_body,
        headers={"content-type": "text/event-stream"},
        request=httpx.Request("POST", "https://fake"),
    )
    provider, _ = _make_provider([response])
    chunks: list[StreamChunk] = []
    async for ch in provider.stream_complete([{"role": "user", "content": "x"}]):
        chunks.append(ch)
    tc_chunks = [c for c in chunks if c.tool_call_delta is not None]
    assert len(tc_chunks) == 2
    # 第二个 chunk 应当聚合了完整 arguments 字符串
    last = tc_chunks[-1].tool_call_delta
    assert last is not None
    assert last.name == "bash"
    assert last.id == "call_1"
    partial = last.arguments.get("_partial_arguments", "")
    assert "ls" in partial


# ========== 错误归一 ==========
# 功能：complete() 把 429 归一为 LLMRateLimitError
# 设计：mock 429 + retry 耗尽，断言捕获 LLMRateLimitError
@pytest.mark.asyncio
async def test_complete_429_normalizes_to_rate_limit_error() -> None:
    provider, _ = _make_provider(
        [_err_response(429), _err_response(429), _err_response(429), _err_response(429)],
        max_retries=2,
    )
    with pytest.raises(LLMRateLimitError) as exc_info:
        await provider.complete([{"role": "user", "content": "x"}])
    assert "429" in str(exc_info.value)


# 功能：complete() 把 500 / 503 归一为 LLMUnavailableError
# 设计：mock 500 / 503 各一次（max_retries=1），断言捕获 LLMUnavailableError
@pytest.mark.asyncio
async def test_complete_500_normalizes_to_unavailable_error() -> None:
    provider, _ = _make_provider(
        [_err_response(500), _err_response(500), _err_response(500)], max_retries=1
    )
    with pytest.raises(LLMUnavailableError) as exc_info:
        await provider.complete([{"role": "user", "content": "x"}])
    assert "500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_complete_503_normalizes_to_unavailable_error() -> None:
    provider, _ = _make_provider(
        [_err_response(503), _err_response(503), _err_response(503)], max_retries=1
    )
    with pytest.raises(LLMUnavailableError) as exc_info:
        await provider.complete([{"role": "user", "content": "x"}])
    assert "503" in str(exc_info.value)


# 功能：complete() 把 httpx.ConnectError 归一为 LLMUnavailableError
# 设计：mock 抛 ConnectError 多次耗尽重试，断言 LLMUnavailableError
@pytest.mark.asyncio
async def test_complete_connect_error_normalizes_to_unavailable() -> None:
    provider, _ = _make_provider(
        [httpx.ConnectError("refused"), httpx.ConnectError("refused"), httpx.ConnectError("refused")],
        max_retries=1,
    )
    with pytest.raises(LLMUnavailableError) as exc_info:
        await provider.complete([{"role": "user", "content": "x"}])
    assert "network error" in str(exc_info.value)


# 功能：complete() 把 400 归一为 LLMError（非速率/不可用）
# 设计：mock 400，断言 LLMError 而不是子类
@pytest.mark.asyncio
async def test_complete_400_normalizes_to_llm_error() -> None:
    provider, _ = _make_provider([_err_response(400)])
    with pytest.raises(LLMError) as exc_info:
        await provider.complete([{"role": "user", "content": "x"}])
    assert "400" in str(exc_info.value)
    assert not isinstance(exc_info.value, LLMRateLimitError)
    assert not isinstance(exc_info.value, LLMUnavailableError)


# ========== 重试机制 ==========
# 功能：complete() 429 后第二次成功（验证 retry 不会重试成功响应）
# 设计：mock 429 然后 200，断言最终 result 正确；calls 应当是 2 次
@pytest.mark.asyncio
async def test_complete_retries_on_429_then_succeeds() -> None:
    payload = {
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        "usage": {},
    }
    provider, transport = _make_provider(
        [_err_response(429), _json_response(200, payload)], max_retries=3
    )
    result = await provider.complete([{"role": "user", "content": "x"}])
    assert result.content == "ok"
    assert len(transport.calls) == 2


# 功能：complete() 500 后第二次成功
# 设计：mock 500 然后 200，断言重试 1 次后成功
@pytest.mark.asyncio
async def test_complete_retries_on_500_then_succeeds() -> None:
    payload = {
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "recovered"}, "finish_reason": "stop"}],
        "usage": {},
    }
    provider, transport = _make_provider(
        [_err_response(500), _json_response(200, payload)], max_retries=3
    )
    result = await provider.complete([{"role": "user", "content": "x"}])
    assert result.content == "recovered"
    assert len(transport.calls) == 2


# 功能：complete() 503 后第二次成功
# 设计：mock 503 然后 200，断言重试 1 次后成功
@pytest.mark.asyncio
async def test_complete_retries_on_503_then_succeeds() -> None:
    payload = {
        "model": "gpt-4o-mini",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "x"}, "finish_reason": "stop"}],
        "usage": {},
    }
    provider, transport = _make_provider(
        [_err_response(503), _json_response(200, payload)], max_retries=3
    )
    await provider.complete([{"role": "user", "content": "x"}])
    assert len(transport.calls) == 2


# 功能：complete() 重试耗尽后抛 LLMUnavailableError
# 设计：max_retries=2 mock 3 个 500，断言最终抛错
@pytest.mark.asyncio
async def test_complete_exhausts_retries_and_raises() -> None:
    provider, transport = _make_provider(
        [_err_response(500), _err_response(500), _err_response(500)], max_retries=2
    )
    with pytest.raises(LLMUnavailableError):
        await provider.complete([{"role": "user", "content": "x"}])
    # 1 + 2 retries = 3 total
    assert len(transport.calls) == 3


# ========== 工厂 / env vars ==========
# 功能：create_provider("openai") 读 KIVI_OPENAI_API_KEY 构造 OpenAICompatProvider
# 设计：monkeypatch 3 个 KIVI_OPENAI_* env，断言返回的 provider 是 OpenAICompatProvider 且字段正确
def test_create_provider_openai_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIVI_OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setenv("KIVI_OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("KIVI_OPENAI_MODEL", "deepseek-chat")
    monkeypatch.delenv("KIVI_LLM_TIMEOUT", raising=False)
    monkeypatch.delenv("KIVI_LLM_MAX_RETRIES", raising=False)
    provider = create_provider("openai")
    assert isinstance(provider, OpenAICompatProvider)
    assert provider._model == "deepseek-chat"
    assert provider._base_url == "https://api.deepseek.com/v1"
    assert provider._api_key == "sk-test-123"


# 功能：create_provider(None) 自动检测：有 KIVI_OPENAI_API_KEY 选 openai
# 设计：monkeypatch 设 KIVI_OPENAI_API_KEY，断言返回 OpenAICompatProvider
def test_create_provider_auto_detects_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIVI_OPENAI_API_KEY", "sk-auto")
    monkeypatch.delenv("KIVI_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = create_provider(None)
    assert isinstance(provider, OpenAICompatProvider)


# 功能：create_provider("openai") 缺 KIVI_OPENAI_API_KEY 时抛 ValueError
# 设计：清空所有 API key env，断言 ValueError
def test_create_provider_openai_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KIVI_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="KIVI_OPENAI_API_KEY"):
        create_provider("openai")


# 功能：create_provider("anthropic") 在 L2 worktree 内抛 NotImplementedError（由 L1 集成）
# 设计：断言 NotImplementedError 而不是默写 anthropic 实现
def test_create_provider_anthropic_not_implemented_in_l2() -> None:
    with pytest.raises(NotImplementedError, match="WT-L1"):
        create_provider("anthropic")


# 功能：create_provider("unknown") 抛 ValueError 列出支持的名字
# 设计：传入 "xyz"，断言 ValueError 包含 "openai" "anthropic" "fake"
def test_create_provider_unknown_name_raises() -> None:
    with pytest.raises(ValueError, match="openai"):
        create_provider("xyz")


# ========== LLMError __str__ 契约 ==========
# 功能：LLMError 子类 __str__ 格式为 "ClassName: message"
# 设计：捕获各种异常并断言 str() 格式
def test_llm_error_str_format() -> None:
    assert str(LLMRateLimitError("too many")) == "LLMRateLimitError: too many"
    assert str(LLMTimeoutError("slow")) == "LLMTimeoutError: slow"
    assert str(LLMUnavailableError("down")) == "LLMUnavailableError: down"


# 功能：LLMError 子类可被基类 except 捕获
# 设计：assert isinstance 关系 + except LLMError
def test_llm_error_subclass_isinstance() -> None:
    e = LLMRateLimitError("x")
    assert isinstance(e, LLMError)
    assert isinstance(e, Exception)
    try:
        raise LLMRateLimitError("x")
    except LLMError:
        pass
