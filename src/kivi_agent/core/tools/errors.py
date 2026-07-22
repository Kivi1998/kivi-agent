from __future__ import annotations


class RateLimitedError(Exception):
    """Raised by a tool when the upstream service is rate-limiting the request."""


class ToolRejectedError(Exception):
    # 由 HookEngine 在 reject=True 的钩子否决工具调用时抛出
    pass
