"""记忆过期策略（Wave 6.1 J2 增强）。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from kivi_agent.core.memory.backend import MemoryAuditEvent, MemoryItem

if TYPE_CHECKING:
    from kivi_agent.core.memory.audit import MemoryAuditLogger
    from kivi_agent.core.memory.backend import MemoryBackend


StatusResult = Literal["active", "expired"]


def _now_iso() -> str:
    """当前 UTC ISO 8601 时间字符串。"""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _parse_iso(ts: str) -> datetime | None:
    """把 ISO 8601 字符串解析为 datetime；解析失败返回 None。"""
    if not ts:
        return None
    s = ts.strip()
    # 处理 Z 结尾
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    # 朴素的 timezone 处理：若 dt 无 tzinfo 则视为 UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


class MemoryExpiryPolicy:
    """记忆过期策略：按 expires_at 判定 active / expired 并自动 archive。"""

    def __init__(self, now_fn: Callable[[], datetime] | None = None) -> None:
        # 注入式 now_fn 便于单测控制时间
        self._now_fn: Callable[[], datetime] = now_fn or (lambda: datetime.now(UTC))

    # 判定单条记忆是否过期。expires_at=None 视为永久 → active。
    def check(self, memory: MemoryItem) -> StatusResult:
        if memory.expires_at is None:
            return "active"
        exp = _parse_iso(memory.expires_at)
        if exp is None:
            # 无法解析 → 保守视为 active
            return "active"
        now = self._now_fn()
        return "active" if now <= exp else "expired"

    # 把过期记忆在 backend 上 archive（status=archived）；返回处理条数。
    # backend 需实现 list_all / update / audit；list_all 由实现可选提供
    # （J2 增强在 LocalMemoryBackend 加）。
    async def archive_expired(
        self,
        backend: MemoryBackend,
        audit_logger: MemoryAuditLogger | None = None,
    ) -> int:
        listed: list[MemoryItem] = []
        list_all = getattr(backend, "list_all", None)
        if callable(list_all):
            res = list_all()
            if hasattr(res, "__await__"):
                listed = list(await res)
            else:
                listed = list(res)
        else:
            # 兜底：search "*" 在多数实现会返回全量；空 query 兜底返回 []
            listed = await backend.search("*", top_k=10000)

        count = 0
        for item in listed:
            if self.check(item) == "expired" and item.status == "active":
                archived = replace(item, status="archived")
                await backend.update(item.id, archived)
                count += 1
                if audit_logger is not None:
                    await audit_logger.record(MemoryAuditEvent(
                        memory_id=item.id,
                        event_type="expire",
                        ts=_now_iso(),
                        actor="system:expiry",
                    ))
        return count

    # 把 expires_at 已到的记忆转 archived 副本（不改 backend），便于上层决定如何处理。
    def to_archived(self, memory: MemoryItem) -> MemoryItem:
        """返回一个 status=archived 的副本，原对象不变。"""
        if memory.status == "archived":
            return memory
        return replace(memory, status="archived")
