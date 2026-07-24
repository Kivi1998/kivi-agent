from __future__ import annotations

import pytest

from kivi_agent.core.llm.errors import (
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)

# --- 基础类 ----------------------------------------------------------------


# 功能：验证 LLMError 可作为基类被实例化并保留原始消息
def test_llm_error_basic_instantiation() -> None:
    err = LLMError("boom")
    assert err.args == ("boom",)
    assert err.__class__.__name__ == "LLMError"


# 功能：验证 LLMError.__str__ 输出格式为 'ClassName: msg'，便于日志一行打印
def test_llm_error_str_format() -> None:
    err = LLMError("network down")
    assert str(err) == "LLMError: network down"


# 功能：验证 LLMError 不带参数时 __str__ 仍输出类名（防御空 args）
def test_llm_error_no_args_str() -> None:
    err = LLMError()
    assert str(err) == "LLMError: "


# --- 子类 ------------------------------------------------------------------


# 功能：验证 4 个子类均为 LLMError 的子类，确保上层 except LLMError 能捕获
@pytest.mark.parametrize(
    "exc_cls",
    [LLMRateLimitError, LLMTimeoutError, LLMUnavailableError, LLMError],
)
def test_subclass_inheritance(exc_cls: type[LLMError]) -> None:
    err = exc_cls("x")
    assert isinstance(err, LLMError)
    assert isinstance(err, Exception)


# 功能：验证 LLMRateLimitError.__str__ 输出包含 'LLMRateLimitError:' 前缀
def test_rate_limit_error_str() -> None:
    err = LLMRateLimitError("429 too many requests")
    assert str(err) == "LLMRateLimitError: 429 too many requests"


# 功能：验证 LLMTimeoutError.__str__ 输出包含 'LLMTimeoutError:' 前缀
def test_timeout_error_str() -> None:
    err = LLMTimeoutError("30s timeout")
    assert str(err) == "LLMTimeoutError: 30s timeout"


# 功能：验证 LLMUnavailableError.__str__ 输出包含 'LLMUnavailableError:' 前缀
def test_unavailable_error_str() -> None:
    err = LLMUnavailableError("503 service unavailable")
    assert str(err) == "LLMUnavailableError: 503 service unavailable"


# --- 可抛出 / 可捕获 ---------------------------------------------------------


# 功能：验证异常可正常抛出并被 except LLMError 捕获（上层重试逻辑依赖此契约）
def test_can_be_raised_and_caught() -> None:
    with pytest.raises(LLMError) as exc_info:
        raise LLMRateLimitError("retry later")
    assert "retry later" in str(exc_info.value)


# 功能：验证子类之间互不兼容：except LLMRateLimitError 不会捕获 LLMTimeoutError
def test_subclass_not_swallowed_by_sibling() -> None:
    with pytest.raises(LLMTimeoutError):
        try:
            raise LLMTimeoutError("oops")
        except LLMRateLimitError:
            pytest.fail("LLMRateLimitError should not catch LLMTimeoutError")
