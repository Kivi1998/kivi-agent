"""记忆提取失败 fallback（Wave 6.1 J2 增强）。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


# 提取结果：ok=False 时 items=[]，主任务继续；error 字段记录异常文本。
class ExtractionResult(TypedDict):
    ok: bool
    items: list[Any]  # 与 extractor 自身返回类型一致（list[MemoryItem] / list[dict]）
    error: str | None


@dataclass
class MemoryExtractionFallback:
    """包装 LLM 提取调用；任何异常时降级返回 ok=False，绝不抛。"""

    # 调用 extractor(*args, **kwargs)；提取器可能返回 list[MemoryItem] / list[dict] / 其它
    # 异常分支永远返回 ok=False + items=[]，主任务继续。
    async def safe_extract(
        self,
        extractor: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> ExtractionResult:
        try:
            res = extractor(*args, **kwargs)
            if hasattr(res, "__await__"):
                res = await res
        except Exception as exc:
            logger.warning(
                "memory extraction fallback: %s failed: %s",
                getattr(extractor, "__name__", repr(extractor)),
                exc,
            )
            return ExtractionResult(ok=False, items=[], error=str(exc))
        if res is None:
            return ExtractionResult(ok=False, items=[], error="extractor returned None")
        if not isinstance(res, list):
            return ExtractionResult(
                ok=False,
                items=[],
                error=f"extractor returned non-list: {type(res).__name__}",
            )
        return ExtractionResult(ok=True, items=res, error=None)

    # 同步包装：对于非 async 提取器同样适用
    def safe_extract_sync(
        self,
        extractor: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> ExtractionResult:
        try:
            res = extractor(*args, **kwargs)
        except Exception as exc:
            logger.warning(
                "memory extraction fallback (sync): %s failed: %s",
                getattr(extractor, "__name__", repr(extractor)),
                exc,
            )
            return ExtractionResult(ok=False, items=[], error=str(exc))
        if res is None:
            return ExtractionResult(ok=False, items=[], error="extractor returned None")
        if not isinstance(res, list):
            return ExtractionResult(
                ok=False,
                items=[],
                error=f"extractor returned non-list: {type(res).__name__}",
            )
        return ExtractionResult(ok=True, items=res, error=None)
