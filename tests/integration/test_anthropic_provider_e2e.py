from __future__ import annotations

import os

import pytest

from kivi_agent.core.llm.errors import LLMError
from kivi_agent.core.llm.factory import create_provider
from kivi_agent.core.llm.provider import (
    AnthropicProvider,
    CompletionResult,
    StreamChunk,
)

# --- env guard -------------------------------------------------------------


# 功能：默认情况下 e2e 测试被 skip（不消耗 token、不依赖外网）
# 设计：KIVI_RUN_E2E=1 才启用；KIVI_ANTHROPIC_API_KEY 必须设置
_RUN_E2E = os.environ.get("KIVI_RUN_E2E") == "1"
_HAS_KEY = bool(os.environ.get("KIVI_ANTHROPIC_API_KEY"))

pytestmark = pytest.mark.skipif(
    not (_RUN_E2E and _HAS_KEY),
    reason="requires KIVI_RUN_E2E=1 and KIVI_ANTHROPIC_API_KEY",
)


# --- helpers ---------------------------------------------------------------


def _build_provider() -> AnthropicProvider:
    # 功能：从 env 构造真 AnthropicProvider（短路：如果 env 不全则 test 已被 skip）
    return create_provider("anthropic", model="claude-sonnet-4-6")  # type: ignore[return-value]


# --- complete() 真 LLM ----------------------------------------------------


# 功能：验证真 LLM complete() 返回有效 CompletionResult（content 非空 / token > 0）
async def test_real_complete_basic() -> None:
    provider = _build_provider()
    result = await provider.complete(
        messages=[{"role": "user", "content": "Reply with exactly: pong"}]
    )
    assert isinstance(result, CompletionResult)
    assert "pong" in result.content.lower()
    assert result.usage.input_tokens > 0
    assert result.usage.output_tokens > 0
    assert result.usage.total_tokens > 0
    assert result.stop_reason == "end_turn"
    assert result.model.startswith("claude")


# 功能：验证真 LLM complete() 支持 tool_use（注入一个简单加法工具）
async def test_real_complete_with_tool_use() -> None:
    provider = _build_provider()
    tools: list[dict[str, object]] = [
        {
            "name": "add",
            "description": "Add two numbers and return the sum.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                "required": ["a", "b"],
            },
        }
    ]
    result = await provider.complete(
        messages=[
            {
                "role": "user",
                "content": "What is 17 + 25? Use the add tool.",
            }
        ],
        tools=tools,
    )
    assert result.stop_reason == "tool_use"
    assert len(result.tool_calls) == 1
    tc = result.tool_calls[0]
    assert tc["name"] == "add"
    assert isinstance(tc["input"], dict)


# --- stream_complete() 真 LLM ---------------------------------------------


# 功能：验证真 LLM stream_complete() 至少 yield 1 个 chunk 且终态 done=True
async def test_real_stream_basic() -> None:
    provider = _build_provider()
    chunks: list[StreamChunk] = []
    async for c in provider.stream_complete(
        messages=[{"role": "user", "content": "Say hi."}]
    ):
        chunks.append(c)
    assert len(chunks) >= 2
    last = chunks[-1]
    assert last.done is True
    assert last.usage is not None
    assert last.usage.input_tokens > 0
    # 拼接 delta 得到完整文本，应包含 'hi' 字样
    text = "".join(c.delta for c in chunks[:-1])
    assert "hi" in text.lower()


# --- error path: 错误被归一化 ----------------------------------------------


# 功能：用一个无效模型触发 API 错误，验证异常被归一化为 LLMError 子类
async def test_real_invalid_model_raises_llm_error() -> None:
    provider = create_provider("anthropic", model="claude-nonexistent-fake")
    assert isinstance(provider, AnthropicProvider)
    with pytest.raises(LLMError):
        await provider.complete(
            messages=[{"role": "user", "content": "hi"}]
        )
