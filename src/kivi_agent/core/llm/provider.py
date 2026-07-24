from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import anthropic
import httpx

from kivi_agent.core.bus.events import LlmModelSelectedEvent, LlmTokenEvent, LlmUsageEvent
from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.llm.catalog import context_window_for
from kivi_agent.core.llm.errors import (
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from kivi_agent.core.llm.types import LlmResponse, ToolCallBlock, UsageStats

_MAX_STREAM_RETRIES = 3
_RETRY_BACKOFF_S = (1.0, 2.0, 4.0)

log = logging.getLogger(__name__)


_SYSTEM_PROMPT = (
    "You are a helpful AI assistant. "
    "Use the available tools to complete the user's goal. "
    "When the goal is fully achieved, respond with a final answer and do not call any more tools."
)


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


# 把 anthropic SDK 异常按 HTTP 语义归一化为本地 LLMError 子类
def _classify_exception(exc: BaseException, *, timeout: float) -> LLMError | None:
    if isinstance(exc, asyncio.TimeoutError):
        return LLMTimeoutError(f"LLM call timed out after {timeout}s")
    if isinstance(exc, anthropic.RateLimitError):
        return LLMRateLimitError(f"Anthropic rate limit: {exc}")
    if isinstance(exc, anthropic.APITimeoutError):
        return LLMTimeoutError(f"Anthropic API timeout: {exc}")
    if isinstance(exc, anthropic.APIStatusError):
        status = getattr(exc, "status_code", None) or 0
        if status in (500, 502, 503, 504):
            return LLMUnavailableError(f"Anthropic {status}: {exc}")
        return LLMError(f"Anthropic API error {status}: {exc}")
    if isinstance(exc, anthropic.APIConnectionError):
        return LLMUnavailableError(f"Anthropic connection error: {exc}")
    return None


# 判断一个异常是否可重试（429 / 5xx / connection / 5xx status）
def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (anthropic.RateLimitError, anthropic.APIConnectionError)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        status = getattr(exc, "status_code", None) or 0
        return status in (500, 502, 503, 504)
    return False


# 从 anthropic Message 对象构造 CompletionResult
def _to_completion_result(response: Any, fallback_model: str) -> CompletionResult:
    content_parts: list[str] = []
    tool_calls: list[dict[str, object]] = []
    for block in response.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            content_parts.append(getattr(block, "text", "") or "")
        elif btype == "tool_use":
            tool_calls.append(
                {
                    "id": getattr(block, "id", "") or "",
                    "name": getattr(block, "name", "") or "",
                    "input": dict(getattr(block, "input", {}) or {}),
                }
            )
    usage_obj = response.usage
    usage = TokenUsage(
        input_tokens=int(getattr(usage_obj, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage_obj, "output_tokens", 0) or 0),
    )
    return CompletionResult(
        content="".join(content_parts),
        tool_calls=tool_calls,
        usage=usage,
        stop_reason=str(getattr(response, "stop_reason", "end_turn") or "end_turn"),
        model=str(getattr(response, "model", fallback_model) or fallback_model),
    )


@dataclass
class TokenUsage:
    # LLM 调用的 token 计数（input / output / total）
    input_tokens: int
    output_tokens: int

    # 返回 input + output 合计 token 数
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class CompletionResult:
    # LLM complete() 调用的归一化结果
    content: str
    tool_calls: list[dict[str, object]]
    usage: TokenUsage
    stop_reason: str
    model: str


@dataclass
class StreamChunk:
    # LLM stream_complete() 增量输出单元；最后一个 chunk 携带 usage 并标 done=True
    delta: str
    usage: TokenUsage | None
    done: bool


class AnthropicProvider:
    # 初始化 Anthropic 客户端；client 可在测试时注入以跳过 API key 检查
    def __init__(
        self,
        model: str,
        client: Any = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> None:
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._max_retries = max_retries
        self._temperature = temperature
        self._max_tokens = max_tokens

        if client is not None:
            self._client: Any = client
            return

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise SystemExit("ANTHROPIC_API_KEY not set")
        client_kwargs: dict[str, Any] = {"api_key": key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = anthropic.AsyncAnthropic(**client_kwargs)

    # 流式调用 Anthropic API，逐 token 发布事件并返回 LlmResponse；网络中断时自动重试
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

        system_blocks: list[dict[str, object]] = [
            {
                "type": "text",
                "text": system or _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            },
        ]

        tools: list[dict[str, object]] = list(tool_schemas)
        if tools:
            last = dict(tools[-1])
            last["cache_control"] = {"type": "ephemeral"}
            tools = tools[:-1] + [last]

        kwargs: dict[str, object] = {
            "model": self._model,
            "max_tokens": 8192,
            "system": system_blocks,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        text_parts: list[str] = []
        final_message: Any = None

        for attempt in range(1, _MAX_STREAM_RETRIES + 1):
            text_parts = []
            try:
                async with self._client.messages.stream(**kwargs) as stream:
                    async for text in stream.text_stream:
                        # Only publish token events on the first attempt to avoid TUI duplicates
                        if attempt == 1:
                            await bus.publish(LlmTokenEvent(run_id=run_id, token=text, ts=_now()))
                        text_parts.append(text)
                    final_message = await stream.get_final_message()
                break  # success
            except (httpx.RemoteProtocolError, httpx.ReadError, httpx.ConnectError) as exc:
                if attempt == _MAX_STREAM_RETRIES:
                    log.error(
                        "stream failed after %d attempts run_id=%s step=%d: %s",
                        _MAX_STREAM_RETRIES, run_id, step, exc,
                    )
                    raise
                delay = _RETRY_BACKOFF_S[attempt - 1]
                log.warning(
                    "stream dropped (attempt %d/%d) run_id=%s step=%d: %s — retrying in %.0fs",
                    attempt, _MAX_STREAM_RETRIES, run_id, step, exc, delay,
                )
                await asyncio.sleep(delay)

        assert final_message is not None

        usage = final_message.usage
        cache_read: int = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_create: int = getattr(usage, "cache_creation_input_tokens", 0) or 0
        context_pct = usage.input_tokens / context_window_for(self._model)

        await bus.publish(
            LlmUsageEvent(
                run_id=run_id,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_input_tokens=cache_read,
                cache_creation_input_tokens=cache_create,
                context_pct=context_pct,
                ts=_now(),
            )
        )

        tool_calls: list[ToolCallBlock] = []
        thinking_blocks: list[dict[str, object]] = []
        for block in final_message.content:
            if block.type == "tool_use":
                tool_calls.append(
                    ToolCallBlock(id=block.id, name=block.name, input=dict(block.input))
                )
            elif block.type == "thinking":
                # thinking blocks must be passed back verbatim in subsequent requests
                thinking_blocks.append({"type": "thinking", "thinking": block.thinking, "signature": block.signature})

        return LlmResponse(
            stop_reason=final_message.stop_reason or "end_turn",
            tool_calls=tool_calls,
            text="".join(text_parts),
            thinking_blocks=thinking_blocks,
            usage=UsageStats(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_input_tokens=cache_read,
                cache_creation_input_tokens=cache_create,
                context_pct=context_pct,
            ),
        )

    # 计算第 N 次重试的退避秒数（指数退避；超出表长时使用最后一个值）
    def _retry_delay(self, attempt: int) -> float:
        idx = min(attempt - 1, len(_RETRY_BACKOFF_S) - 1)
        return _RETRY_BACKOFF_S[idx]

    # 非流式调用；429/5xx 指数退避重试；超时归一化为 LLMTimeoutError
    async def complete(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
    ) -> CompletionResult:
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "messages": messages,
        }
        if tools:
            payload["tools"] = list(tools)

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                delay = self._retry_delay(attempt)
                log.warning(
                    "anthropic retry attempt=%d/%d delay=%.0fs",
                    attempt, self._max_retries, delay,
                )
                await asyncio.sleep(delay)
            try:
                response = await asyncio.wait_for(
                    self._client.messages.create(**payload),
                    timeout=self._timeout,
                )
                return _to_completion_result(response, self._model)
            except TimeoutError as exc:
                raise LLMTimeoutError(
                    f"LLM call timed out after {self._timeout}s"
                ) from exc
            except Exception as exc:  # noqa: BLE001 - 顶层捕获后做归一化
                classified = _classify_exception(exc, timeout=self._timeout)
                if classified is None:
                    raise
                last_exc = exc
                if _is_retryable(exc) and attempt < self._max_retries:
                    continue
                raise classified from exc

        # 理论上不可达（最后一次循环要么成功要么 raise），保底抛 LLMError
        raise LLMError(f"LLM call failed after {self._max_retries} retries: {last_exc}")

    # 流式调用；按 text_stream 增量 yield StreamChunk；最后一块携带 usage 并标 done=True
    async def stream_complete(
        self,
        messages: list[dict[str, object]],
    ) -> AsyncIterator[StreamChunk]:
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "messages": messages,
        }

        last_exc: BaseException | None = None
        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                delay = self._retry_delay(attempt)
                log.warning(
                    "anthropic stream retry attempt=%d/%d delay=%.0fs",
                    attempt, self._max_retries, delay,
                )
                await asyncio.sleep(delay)
            try:
                async with self._client.messages.stream(**payload) as stream:
                    async for text in stream.text_stream:
                        yield StreamChunk(delta=text, usage=None, done=False)
                    final = await stream.get_final_message()
                    usage_obj = final.usage
                    yield StreamChunk(
                        delta="",
                        usage=TokenUsage(
                            input_tokens=int(getattr(usage_obj, "input_tokens", 0) or 0),
                            output_tokens=int(getattr(usage_obj, "output_tokens", 0) or 0),
                        ),
                        done=True,
                    )
                    return
            except TimeoutError as exc:
                raise LLMTimeoutError(
                    f"LLM stream timed out after {self._timeout}s"
                ) from exc
            except Exception as exc:  # noqa: BLE001
                classified = _classify_exception(exc, timeout=self._timeout)
                if classified is None:
                    raise
                last_exc = exc
                if _is_retryable(exc) and attempt < self._max_retries:
                    continue
                raise classified from exc

        raise LLMError(f"LLM stream failed after {self._max_retries} retries: {last_exc}")
