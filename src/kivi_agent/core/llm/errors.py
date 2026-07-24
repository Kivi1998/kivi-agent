from __future__ import annotations


# LLM 调用的统一异常基类；4 个子类按 HTTP 状态语义拆分
class LLMError(Exception):
    # 返回一行格式化错误信息：ClassName: 原始消息，便于日志直接 print
    def __str__(self) -> str:
        msg = self.args[0] if self.args else ""
        return f"{self.__class__.__name__}: {msg}"


# 429 限流错误：触发指数退避重试，超过 max_retries 后抛出
class LLMRateLimitError(LLMError):
    pass


# 请求超时错误：asyncio.wait_for 触发或远端 APITimeoutError
class LLMTimeoutError(LLMError):
    pass


# 5xx 服务不可用错误：触发指数退避重试，超过 max_retries 后抛出
class LLMUnavailableError(LLMError):
    pass


__all__ = ["LLMError", "LLMRateLimitError", "LLMTimeoutError", "LLMUnavailableError"]
