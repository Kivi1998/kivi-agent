from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from kivi_agent.core.bus.events import LlmModelSelectedEvent, LlmTokenEvent, LlmUsageEvent
from kivi_agent.core.config import KamaConfig
from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.llm.base import LLMProvider
from kivi_agent.core.llm.openai_compat_provider import OpenAICompatProvider
from kivi_agent.core.llm.provider import (
    AnthropicProvider,
    CompletionResult,
    StreamChunk,
    TokenUsage,
)
from kivi_agent.core.llm.types import LlmResponse


# 解析 KIVI_LLM_TIMEOUT 环境变量（带异常保护，默认 30s）
def _read_timeout() -> float:
    raw = os.environ.get("KIVI_LLM_TIMEOUT")
    if not raw:
        return 30.0
    try:
        return float(raw)
    except ValueError:
        return 30.0


# 解析 KIVI_LLM_MAX_RETRIES 环境变量（带异常保护，默认 3）
def _read_max_retries() -> int:
    raw = os.environ.get("KIVI_LLM_MAX_RETRIES")
    if not raw:
        return 3
    try:
        return int(raw)
    except ValueError:
        return 3


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


# 无 API key 时使用的占位 provider（保留 Wave 1 行为：调用 chat() 返回 canned response）
class _FakeLLMProvider:
    # 初始化；model 记录用于日志 / 事件中的模型名
    def __init__(self, model: str) -> None:
        self._model = model

    # 实现 LLMProvider Protocol：发布 3 个事件并返回 canned LlmResponse
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
            LlmModelSelectedEvent(
                run_id=run_id, model=self._model, strategy="static", ts=_now()
            )
        )
        fake_text = f"[fake:{self._model}] no API key configured"
        await bus.publish(
            LlmTokenEvent(run_id=run_id, token=fake_text, ts=_now())
        )
        await bus.publish(
            LlmUsageEvent(
                run_id=run_id,
                input_tokens=0,
                output_tokens=0,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                context_pct=0.0,
                ts=_now(),
            )
        )
        return LlmResponse(stop_reason="end_turn", text=fake_text)

    # 新接口：非流式 complete()，返回 canned CompletionResult
    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
    ) -> CompletionResult:
        return CompletionResult(
            content=f"[fake:{self._model}] no API key configured",
            tool_calls=[],
            usage=TokenUsage(input_tokens=0, output_tokens=0),
            stop_reason="end_turn",
            model=self._model,
        )

    # 新接口：流式 stream_complete()，yield 一段文本 + 终态 chunk
    async def stream_complete(
        self,
        messages: list[dict[str, object]],
    ) -> Any:
        yield StreamChunk(
            delta=f"[fake:{self._model}] ", usage=None, done=False
        )
        yield StreamChunk(delta="no API key configured", usage=None, done=False)
        yield StreamChunk(
            delta="",
            usage=TokenUsage(input_tokens=0, output_tokens=0),
            done=True,
        )


# 根据配置构造对应的 LLMProvider 实例（Anthropic 或 OpenAI 兼容）
def build_provider(config: KamaConfig) -> LLMProvider:
    if config.llm.provider == "openai_compat":
        base_url = config.llm.openai_base_url
        if not base_url:
            raise SystemExit("llm.openai_base_url must be set when llm.provider = 'openai_compat'")
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise SystemExit("OPENAI_API_KEY not set")
        return OpenAICompatProvider(config.llm.default_model, base_url=base_url, api_key=api_key)
    return AnthropicProvider(config.llm.default_model)


# 按 KIVI_* env vars 构造 provider；无 key 时回退到 fake 占位（保留 Wave 1 行为）
def create_provider(
    provider_name: str = "anthropic",
    model: str | None = None,
) -> LLMProvider:
    default_model = model or os.environ.get("KIVI_LLM_DEFAULT_MODEL") or "claude-sonnet-4-6"

    if provider_name == "fake":
        return _FakeLLMProvider(model=default_model)

    if provider_name == "anthropic":
        api_key = os.environ.get("KIVI_ANTHROPIC_API_KEY")
        if not api_key:
            return _FakeLLMProvider(model=default_model)
        base_url = os.environ.get("KIVI_ANTHROPIC_BASE_URL")
        return AnthropicProvider(
            model=default_model,
            api_key=api_key,
            base_url=base_url,
            timeout=_read_timeout(),
            max_retries=_read_max_retries(),
        )

    if provider_name == "openai_compat":
        api_key = os.environ.get("KIVI_OPENAI_API_KEY")
        if not api_key:
            return _FakeLLMProvider(model=default_model)
        # L2 (WT-L2) 将增强 OpenAI 兼容分支（DeepSeek / 流式 / Embedding 等）
        base_url = os.environ.get("KIVI_OPENAI_BASE_URL") or "https://api.openai.com/v1"
        return OpenAICompatProvider(
            model=default_model, base_url=base_url, api_key=api_key
        )

    raise ValueError(f"Unknown provider: {provider_name!r}")
