"""OpenAI 兼容 LLM Provider（Wave 8.2 / agent: real-llm-e2e）。

支持：
- OpenAI 官方 / DeepSeek / Azure OpenAI / 任何 OpenAI Chat Completions 兼容端点
- 同步调用 `complete()` 与 SSE 流式 `stream_complete()`（httpx 直连，不绑 openai 库）
- 重试（429 / 500 / 503 exponential backoff）+ 超时（asyncio.wait_for）
- 错误归一化为 `LLMError` / `LLMRateLimitError` / `LLMTimeoutError` / `LLMUnavailableError`
- 保留旧 `chat()` 方法以满足 LLMProvider 协议（bus 事件 + LlmResponse）

设计要点：
- httpx 直连：max 兼容性（DeepSeek 自定义 endpoint / 私有网关）
- 单飞 client：未注入时 lazy 构造；注入的 client 由调用方管理生命周期
- 重试不嵌套：外层循环 + 内部捕获，避免 retry 逻辑写两遍
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx

from kivi_agent.core.bus.events import LlmModelSelectedEvent, LlmTokenEvent, LlmUsageEvent
from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.llm.catalog import context_window_for
from kivi_agent.core.llm.errors import (
    CompletionResult,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
    StreamChunk,
    TokenUsage,
    ToolCall,
)
from kivi_agent.core.llm.streaming import StreamAccumulator
from kivi_agent.core.llm.types import LlmResponse, UsageStats

log = logging.getLogger(__name__)

# 默认 HTTP timeout / 最大重试次数
_DEFAULT_TIMEOUT_S = 30.0
_DEFAULT_MAX_RETRIES = 3
# 指数退避：1s / 2s / 4s / 8s（截顶避免 sleep 太久）
_RETRY_BACKOFF_S = (1.0, 2.0, 4.0, 8.0)
# 触发重试的 HTTP 状态码
_RETRY_STATUSES = frozenset({429, 500, 503, 504})


# 返回当前 UTC 时间的 ISO 8601 字符串
def _now() -> str:
    return datetime.now(UTC).isoformat()


# 把 Anthropic 风格的工具 schema 转成 OpenAI function-calling 格式
def _convert_tool_schema(tool: dict[str, object]) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


# 把上游 HTTP 状态码归一为 LLMError 子类
def _classify_status(status_code: int, url: str) -> LLMError:
    if status_code == 429:
        return LLMRateLimitError(f"HTTP 429 from {url}")
    if 500 <= status_code < 600:
        return LLMUnavailableError(f"HTTP {status_code} from {url}")
    return LLMError(f"HTTP {status_code} from {url}")


# 把 httpx 异常归一为 LLMError 子类
def _classify_httpx_exc(exc: BaseException, url: str) -> LLMError:
    if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError)):
        return LLMTimeoutError(f"timeout calling {url}: {exc}")
    if isinstance(
        exc,
        (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError, httpx.NetworkError),
    ):
        return LLMUnavailableError(f"network error from {url}: {exc}")
    if isinstance(exc, httpx.HTTPStatusError):
        return _classify_status(exc.response.status_code, str(exc.request.url))
    return LLMError(f"{type(exc).__name__} from {url}: {exc}")


# 计算第 n 次重试的退避秒数（截顶到 8s）
def _backoff(attempt: int) -> float:
    if attempt < 0:
        attempt = 0
    return _RETRY_BACKOFF_S[min(attempt, len(_RETRY_BACKOFF_S) - 1)]


# 解析 OpenAI Chat Completions 响应（完整 message）成 CompletionResult
def _parse_completion(data: dict[str, Any]) -> CompletionResult:
    choices = data.get("choices") or [{}]
    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content") or ""
    # 默认空字符串（OpenAI 工具调用返回 content=null）
    if content is None:
        content = ""
    tool_calls_data = message.get("tool_calls") or []
    tool_calls: list[ToolCall] = []
    for tc in tool_calls_data:
        func = tc.get("function") or {}
        args_str = func.get("arguments") or ""
        if isinstance(args_str, str):
            try:
                args: dict[str, Any] = json.loads(args_str) if args_str else {}
            except json.JSONDecodeError:
                # 上游偶尔返回截断/非法 JSON —— 保留原文避免 500
                args = {"_raw_arguments": args_str}
        else:
            args = dict(args_str) if args_str else {}
        tool_calls.append(
            ToolCall(
                id=tc.get("id") or "",
                name=func.get("name") or "",
                arguments=args,
            )
        )
    usage_data = data.get("usage") or {}
    usage = TokenUsage(
        input_tokens=int(usage_data.get("prompt_tokens") or 0),
        output_tokens=int(usage_data.get("completion_tokens") or 0),
        total_tokens=int(usage_data.get("total_tokens") or 0),
    )
    finish = choice.get("finish_reason") or "stop"
    return CompletionResult(
        content=content,
        tool_calls=tool_calls,
        usage=usage,
        stop_reason=str(finish),
        model=str(data.get("model") or ""),
    )


class OpenAICompatProvider:
    """OpenAI 兼容 Chat Completions Provider。"""

    # 初始化：model / base_url / api_key 必填；其余有合理默认；client 可注入（测试用）
    def __init__(
        self,
        model: str,
        *,
        base_url: str,
        api_key: str,
        timeout: float = _DEFAULT_TIMEOUT_S,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        client: Any = None,
    ) -> None:
        self._model = model
        # 去掉尾斜杠避免 /chat/completions 拼成 //chat/completions
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max(0, max_retries)
        self._temperature = temperature
        self._max_tokens = max_tokens
        # 注入的 client 由外部管理；内部 lazy 构造的由 self._owns_client 标识
        self._injected_client: Any = client
        self._owns_client: bool = client is None
        # 类型保持 Any：chat() 走 AsyncOpenAI，complete()/stream_complete() 走 httpx；
        # 注入的 mock client 可能是任意形状，用 Any 兼容。
        self._client: Any = None

    # 拿到 client（按 ownership 决定 lazy 构造还是返回注入对象）
    def _get_client(self) -> Any:
        if self._client is None:
            if self._injected_client is not None:
                self._client = self._injected_client
            else:
                self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    # 关闭内部 client（注入的 client 不主动 close）
    async def aclose(self) -> None:
        if self._client is not None and self._owns_client and hasattr(self._client, "aclose"):
            await self._client.aclose()
            self._client = None

    # 构造 OpenAI Chat Completions 请求体（messages / tools / temperature / max_tokens）
    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        stream: bool = False,
    ) -> dict[str, Any]:
        # 上游 messages 已经是 OpenAI 格式；system 也直接传
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": list(messages),
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if tools:
            payload["tools"] = [_convert_tool_schema(t) for t in tools]
        if stream:
            payload["stream"] = True
            # 多数 OpenAI 兼容服务支持 stream_options.include_usage 以拿到总用量
            payload["stream_options"] = {"include_usage": True}
        return payload

    # 同步 POST + retry/timeout/错误归一（核心内部方法）
    async def _post_with_retry(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        last_err: LLMError | None = None
        # 总尝试 = 1 + max_retries
        total_attempts = self._max_retries + 1
        for attempt in range(total_attempts):
            client = self._get_client()
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            }
            try:
                resp = await client.post(url, json=payload, headers=headers)
            except (TimeoutError, httpx.TimeoutException) as exc:
                last_err = _classify_httpx_exc(exc, url)
                if attempt >= self._max_retries:
                    raise last_err from exc
                await asyncio.sleep(_backoff(attempt))
                continue
            except (
                httpx.ConnectError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.NetworkError,
            ) as exc:
                last_err = _classify_httpx_exc(exc, url)
                if attempt >= self._max_retries:
                    raise last_err from exc
                await asyncio.sleep(_backoff(attempt))
                continue

            if resp.status_code in _RETRY_STATUSES:
                last_err = _classify_status(resp.status_code, url)
                if attempt >= self._max_retries:
                    raise last_err
                await asyncio.sleep(_backoff(attempt))
                continue

            # 非重试状态码
            if resp.status_code >= 400:
                # 包含 body 前 200 字符便于排错
                body = (resp.text or "")[:200]
                raise LLMError(f"HTTP {resp.status_code} from {url}: {body}")

            try:
                data: dict[str, Any] = resp.json()
            except json.JSONDecodeError as exc:
                raise LLMError(f"invalid JSON from {url}: {exc}") from exc
            if not isinstance(data, dict):
                raise LLMError(f"unexpected response shape from {url}: not a JSON object")
            return data

        # 走到这里说明重试耗尽但循环没 raise（不应发生，防御性）
        if last_err is not None:
            raise last_err
        raise LLMUnavailableError(f"exhausted {self._max_retries} retries for {url}")

    # 非流式 Chat Completions 调用；返回 CompletionResult
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> CompletionResult:
        """调用 OpenAI Chat Completions 同步接口；支持工具调用。"""
        url = f"{self._base_url}/chat/completions"
        payload = self._build_payload(messages, tools, stream=False)
        data = await self._post_with_retry(url, payload)
        return _parse_completion(data)

    # 流式 Chat Completions 调用（SSE）；逐 chunk 产出 StreamChunk
    async def stream_complete(
        self, messages: list[dict[str, Any]]
    ) -> AsyncIterator[StreamChunk]:
        """SSE 流式 Chat Completions；逐 chunk 产出 StreamChunk。"""
        url = f"{self._base_url}/chat/completions"
        payload = self._build_payload(messages, tools=None, stream=True)
        total_attempts = self._max_retries + 1
        last_err: LLMError | None = None
        for attempt in range(total_attempts):
            client = self._get_client()
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                "Accept": "text/event-stream",
            }
            try:
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    if resp.status_code in _RETRY_STATUSES:
                        last_err = _classify_status(resp.status_code, url)
                        if attempt >= self._max_retries:
                            raise last_err
                        await asyncio.sleep(_backoff(attempt))
                        continue
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", errors="replace")[:200]
                        raise LLMError(f"HTTP {resp.status_code} from {url}: {body}")
                    # 进入流式消费
                    tool_buffers: dict[int, dict[str, str]] = {}
                    async for raw_line in resp.aiter_lines():
                        if not raw_line:
                            continue
                        # SSE 行：data: <json> 或 data: [DONE]
                        if not raw_line.startswith("data:"):
                            continue
                        chunk = raw_line[5:].strip()
                        if chunk == "[DONE]":
                            break
                        try:
                            evt = json.loads(chunk)
                        except json.JSONDecodeError:
                            continue
                        # 1) usage chunk（stream_options.include_usage=True 时会单独出现）
                        usage_data = evt.get("usage")
                        if usage_data and not evt.get("choices"):
                            yield StreamChunk(
                                usage=TokenUsage(
                                    input_tokens=int(usage_data.get("prompt_tokens") or 0),
                                    output_tokens=int(usage_data.get("completion_tokens") or 0),
                                    total_tokens=int(usage_data.get("total_tokens") or 0),
                                )
                            )
                            continue
                        # 2) content / tool_call / finish_reason chunk
                        for ch in evt.get("choices") or []:
                            delta = ch.get("delta") or {}
                            content = delta.get("content") or ""
                            finish_reason = ch.get("finish_reason")
                            tc_obj: ToolCall | None = None
                            for tc in delta.get("tool_calls") or []:
                                func = tc.get("function") or {}
                                idx = int(tc.get("index") or 0)
                                buf = tool_buffers.setdefault(
                                    idx, {"id": "", "name": "", "args": ""}
                                )
                                if tc.get("id"):
                                    buf["id"] = str(tc["id"])
                                if func.get("name"):
                                    buf["name"] = str(func["name"])
                                if func.get("arguments"):
                                    buf["args"] += str(func["arguments"])
                                tc_obj = ToolCall(
                                    id=buf["id"] or str(tc.get("id") or ""),
                                    name=buf["name"] or str(func.get("name") or ""),
                                    # 流式片段，未聚合为完整 JSON；调用方自行拼接
                                    arguments={"_partial_arguments": buf["args"]},
                                )
                            usage = None
                            if usage_data:
                                usage = TokenUsage(
                                    input_tokens=int(usage_data.get("prompt_tokens") or 0),
                                    output_tokens=int(usage_data.get("completion_tokens") or 0),
                                    total_tokens=int(usage_data.get("total_tokens") or 0),
                                )
                            if content or tc_obj or finish_reason or usage:
                                yield StreamChunk(
                                    content=content,
                                    tool_call_delta=tc_obj,
                                    finish_reason=finish_reason,
                                    usage=usage,
                                )
                    return  # 成功完成
            except (TimeoutError, httpx.TimeoutException) as exc:
                last_err = _classify_httpx_exc(exc, url)
                if attempt >= self._max_retries:
                    raise last_err from exc
                await asyncio.sleep(_backoff(attempt))
                continue
            except (
                httpx.ConnectError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.NetworkError,
            ) as exc:
                last_err = _classify_httpx_exc(exc, url)
                if attempt >= self._max_retries:
                    raise last_err from exc
                await asyncio.sleep(_backoff(attempt))
                continue

        if last_err is not None:
            raise last_err
        raise LLMUnavailableError(f"stream exhausted {self._max_retries} retries for {url}")

    # ---- LLMProvider 协议入口（旧接口，保留 bus 事件 + LlmResponse）----
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
        """保留旧 bus 事件契约；走 AsyncOpenAI 流式（与 Wave 1 行为一致）。"""
        from openai import AsyncOpenAI  # 延迟导入：保持新方法不依赖 openai 库

        await bus.publish(
            LlmModelSelectedEvent(run_id=run_id, model=self._model, strategy="static", ts=_now())
        )

        # 优先使用注入的 client（测试）；否则构造 AsyncOpenAI（生产）
        # 类型 Any 兼容：注入 mock 含 .chat.completions.create，AsyncOpenAI 同样
        if self._injected_client is not None:
            client: Any = self._injected_client
        else:
            client = AsyncOpenAI(base_url=self._base_url, api_key=self._api_key)
        openai_messages: list[dict[str, object]] = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        openai_messages.extend(messages)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": openai_messages,
            "stream": True,
        }
        if tool_schemas:
            kwargs["tools"] = [_convert_tool_schema(t) for t in tool_schemas]
        stream = await client.chat.completions.create(**kwargs)
        return await self._accumulate_stream(stream, bus, run_id)

    # 把 AsyncOpenAI 流式 chunk 聚合成 LlmResponse
    async def _accumulate_stream(self, stream: Any, bus: EventBus, run_id: str) -> LlmResponse:
        acc = StreamAccumulator()
        usage: Any = None
        async for chunk in stream:
            if not chunk.choices:
                continue
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


__all__ = ["OpenAICompatProvider"]
