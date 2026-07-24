"""LLM Provider 工厂（Wave 8.2 / agent: real-llm-e2e）。

`build_provider(config)` —— 旧接口（基于 KamaConfig），保留以兼容现有调用。
`create_provider(provider_name, model=None)` —— 新接口（基于 provider_name + env vars）：
- L1（WT-L1）填充 anthropic / fake 分支（含 KIVI_ANTHROPIC_* env vars）
- L2（WT-L2）填充 openai_compat 分支（DeepSeek 兼容 + KIVI_OPENAI_* env vars）
- 主控 integration/aigroup-wave8-2 整合两份实现
"""
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
    def __init__(self, model: str) -> None:
        self._model = model

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


# 根据配置构造对应的 LLMProvider 实例（旧接口，兼容 KamaConfig）
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


# ---- 内部：构造 OpenAI 兼容 provider（WT-L2 增强版） ----
def _create_openai_provider(
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float | None = None,
    max_retries: int | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    client: object | None = None,
) -> OpenAICompatProvider:
    """构造 OpenAI 兼容 provider；参数优先级：显式 > env > 库默认。"""
    resolved_model = (
        model
        or os.environ.get("KIVI_OPENAI_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or "gpt-4o-mini"
    )
    resolved_base = (
        base_url
        or os.environ.get("KIVI_OPENAI_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    )
    resolved_key = (
        api_key
        or os.environ.get("KIVI_OPENAI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    )
    if not resolved_key:
        raise ValueError(
            "OpenAI provider requires KIVI_OPENAI_API_KEY (or OPENAI_API_KEY) env var"
        )
    if timeout is None:
        env_timeout = os.environ.get("KIVI_LLM_TIMEOUT")
        timeout = float(env_timeout) if env_timeout else 30.0
    if max_retries is None:
        env_retries = os.environ.get("KIVI_LLM_MAX_RETRIES")
        max_retries = int(env_retries) if env_retries else 3
    if temperature is None:
        temperature = 0.7
    if max_tokens is None:
        max_tokens = 4096
    return OpenAICompatProvider(
        model=resolved_model,
        base_url=resolved_base,
        api_key=resolved_key,
        timeout=timeout,
        max_retries=max_retries,
        temperature=temperature,
        max_tokens=max_tokens,
        client=client,  # type: ignore[arg-type]
    )


# 按 provider_name + env vars 构造 provider；无 key 时回退到 fake 占位
def create_provider(
    provider_name: str = "anthropic",
    model: str | None = None,
) -> LLMProvider:
    """统一 provider 工厂。

    Args:
        provider_name: "anthropic" | "openai_compat" | "fake"（默认 anthropic）
        model: 可选覆盖默认模型

    Returns:
        对应的 LLMProvider 实例；无 API key 时回退 fake
    """
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
        # 委托给 L2 增强版 _create_openai_provider（DeepSeek 兼容 + 完整 env vars）
        try:
            return _create_openai_provider(model=model or default_model)
        except ValueError:
            # 缺 key 时回退 fake（保留 Wave 1 行为）
            return _FakeLLMProvider(model=default_model)

    raise ValueError(f"Unknown provider: {provider_name!r}")
