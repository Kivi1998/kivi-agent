"""LLM 错误类型 + 统一返回结构（Wave 8.2 / agent: real-llm-e2e）。

本模块在 L1（AnthropicProvider 增强）与 L2（OpenAICompatProvider 增强）之间共享，
两边在各自 worktree 中按相同契约实现，集成时由主控 reconcile。

错误层级：
    LLMError (Exception)
    ├── LLMRateLimitError          # HTTP 429
    ├── LLMTimeoutError            # 网络 / SDK 超时
    └── LLMUnavailableError        # HTTP 5xx / 网关失败

返回结构：
    CompletionResult   # complete() 的非流式结果
    TokenUsage         # input / output / total tokens
    StreamChunk        # stream_complete() 的单次增量
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# LLM 调用相关异常的基类
class LLMError(Exception):
    """所有 LLM 相关异常的根类型。"""

    # 把异常格式化为 "ClassName: message"，便于日志/单测断言
    def __str__(self) -> str:
        msg = self.args[0] if self.args else ""
        return f"{self.__class__.__name__}: {msg}"


# 上游返回 HTTP 429（rate limit / quota exceeded）
class LLMRateLimitError(LLMError):
    """429 限流异常。"""


# 调用超时（含 SDK TimeoutError 与 asyncio.wait_for 抛出）
class LLMTimeoutError(LLMError):
    """调用超时异常。"""


# 上游返回 5xx 或网络层失败（connect / read error）
class LLMUnavailableError(LLMError):
    """服务暂时不可用异常。"""


# 单次工具调用的描述（与 LlmResponse 内的 ToolCallBlock 字段保持一致）
@dataclass
class ToolCall:
    """单次工具调用：OpenAI function-calling 格式。"""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


# Token 用量统计（OpenAI 兼容：prompt / completion / total）
@dataclass
class TokenUsage:
    """Token 用量统计。"""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    # 兼容 OpenAI 完整 usage 字段（视上游协议可能存在 cache_* 等）
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


# 流式响应的单次增量（文本 / 工具调用 / 结束原因）
@dataclass
class StreamChunk:
    """stream_complete() 的一次增量。"""

    # 文本增量（可能为空；与 OpenAI delta.content 对应）
    content: str = ""
    # 工具调用增量；同一 index 的多次 chunk 需由调用方聚合
    tool_call_delta: ToolCall | None = None
    # 终止原因（仅最后一块非空）："stop" / "tool_calls" / "length" / "content_filter"
    finish_reason: str | None = None
    # 本次调用的总用量（仅最后一块可能非空）
    usage: TokenUsage | None = None


# complete() 的非流式返回结果
@dataclass
class CompletionResult:
    """非流式调用的最终结果。"""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: TokenUsage = field(default_factory=TokenUsage)
    # OpenAI 风格："stop" / "tool_calls" / "length" / "content_filter"
    stop_reason: str = "stop"
    # 实际服务的模型标识（与请求 model 可能不同 —— 某些网关会回写别名）
    model: str = ""


__all__ = [
    "LLMError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMUnavailableError",
    "TokenUsage",
    "StreamChunk",
    "ToolCall",
    "CompletionResult",
]
