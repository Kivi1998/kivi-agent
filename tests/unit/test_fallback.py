from __future__ import annotations

import pytest

from kivi_agent.core.memory.fallback import MemoryExtractionFallback


# 功能：正常提取器返回 list 时透传
# 设计：构造一个返回 [1, 2, 3] 的同步函数，断言 ok=True + items 一致
def test_safe_extract_passes_through_normal_result() -> None:
    fb = MemoryExtractionFallback()
    def extractor() -> list[int]:
        return [1, 2, 3]
    res = fb.safe_extract_sync(extractor)
    assert res["ok"] is True
    assert res["items"] == [1, 2, 3]
    assert res["error"] is None


# 功能：提取器抛异常时降级返回 ok=False，绝不 raise
# 设计：构造 raise ValueError 的提取器，断言 ok=False + items=[] + error 含异常文本
def test_safe_extract_swallows_exception() -> None:
    fb = MemoryExtractionFallback()
    def bad() -> list[int]:
        raise ValueError("ES unavailable")
    res = fb.safe_extract_sync(bad)
    assert res["ok"] is False
    assert res["items"] == []
    assert res["error"] is not None
    assert "ES unavailable" in res["error"]


# 功能：async 提取器抛异常也降级
# 设计：构造一个 async 抛 RuntimeError 的提取器，await safe_extract 后断言 ok=False
@pytest.mark.asyncio
async def test_safe_extract_async_swallows() -> None:
    fb = MemoryExtractionFallback()
    async def bad() -> list[int]:
        raise RuntimeError("LLM timeout")
    res = await fb.safe_extract(bad)
    assert res["ok"] is False
    assert res["items"] == []
    assert "LLM timeout" in res["error"]


# 功能：解析失败（返回非 list）也降级
# 设计：提取器返回 dict（不是 list），断言 ok=False + 错误说明
def test_safe_extract_handles_non_list() -> None:
    fb = MemoryExtractionFallback()
    def bad() -> dict[str, int]:
        return {"a": 1}  # type: ignore[return-value]
    res = fb.safe_extract_sync(bad)
    assert res["ok"] is False
    assert "non-list" in res["error"] or "None" in res["error"] or res["error"] is not None


# 功能：提取器返回 None 时降级
# 设计：边界条件
def test_safe_extract_handles_none_return() -> None:
    fb = MemoryExtractionFallback()
    def bad() -> None:
        return None
    res = fb.safe_extract_sync(bad)
    assert res["ok"] is False
    assert res["items"] == []
    assert res["error"] is not None


# 功能：async 提取器正常路径
# 设计：构造一个 async 返回 list 的提取器，断言 ok=True
@pytest.mark.asyncio
async def test_safe_extract_async_normal_path() -> None:
    fb = MemoryExtractionFallback()
    async def good() -> list[str]:
        return ["item1", "item2"]
    res = await fb.safe_extract(good)
    assert res["ok"] is True
    assert res["items"] == ["item1", "item2"]


# 功能：异常类型是 KeyError 时也吞掉
# 设计：异常分支覆盖不同异常类型
def test_safe_extract_keyerror() -> None:
    fb = MemoryExtractionFallback()
    def bad() -> list[int]:
        raise KeyError("missing")
    res = fb.safe_extract_sync(bad)
    assert res["ok"] is False
    assert "missing" in res["error"]


# 功能：safe_extract 在 sync 路径下永不 raise
# 设计：连续调用多种异常类型，断言所有调用都正常返回 dict
def test_safe_extract_sync_never_raises() -> None:
    fb = MemoryExtractionFallback()
    exceptions = [ValueError, RuntimeError, KeyError, TypeError, OSError, ZeroDivisionError]
    for exc in exceptions:
        def bad() -> list[int]:
            raise exc("boom")
        # 任何异常都吞掉，断言调用返回
        res = fb.safe_extract_sync(bad)
        assert res["ok"] is False
        assert "boom" in res["error"]


# 功能：async safe_extract 在异常时永不 raise
# 设计：覆盖 async 异常路径
@pytest.mark.asyncio
async def test_safe_extract_async_never_raises() -> None:
    fb = MemoryExtractionFallback()
    async def bad() -> list[int]:
        raise ZeroDivisionError("async boom")
    res = await fb.safe_extract(bad)
    assert res["ok"] is False
    assert "async boom" in res["error"]


# 功能：safe_extract 接受位置参数透传
# 设计：构造一个 sum(a, b) 函数，断言参数被正确转发
def test_safe_extract_passes_positional_args() -> None:
    fb = MemoryExtractionFallback()
    def add(a: int, b: int) -> list[int]:
        return [a + b]
    res = fb.safe_extract_sync(add, 2, 3)
    assert res["ok"] is True
    assert res["items"] == [5]


# 功能：safe_extract 接受 keyword 参数透传
# 设计：构造一个接受 kwargs 的函数
def test_safe_extract_passes_kwargs() -> None:
    fb = MemoryExtractionFallback()
    def make(multiplier: int = 1) -> list[int]:
        return [x * multiplier for x in [1, 2, 3]]
    res = fb.safe_extract_sync(make, multiplier=10)
    assert res["ok"] is True
    assert res["items"] == [10, 20, 30]
