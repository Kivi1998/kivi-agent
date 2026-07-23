from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from kivi_agent.core.memory.audit import MemoryAuditLogger
from kivi_agent.core.memory.backend import MemoryItem
from kivi_agent.core.memory.expire import MemoryExpiryPolicy
from kivi_agent.core.memory.local_backend import LocalMemoryBackend


# 功能：check 在 expires_at=None 时返回 active
# 设计：永久记忆不过期
def test_check_none_expires_at_is_active() -> None:
    policy = MemoryExpiryPolicy()
    m = MemoryItem(
        id="m-1", content="x", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z", expires_at=None,
    )
    assert policy.check(m) == "active"


# 功能：check 在 expires_at 未来时间时返回 active
# 设计：未来过期 → 仍 active
def test_check_future_expires_at_is_active() -> None:
    future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    policy = MemoryExpiryPolicy()
    m = MemoryItem(
        id="m-1", content="x", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z", expires_at=future,
    )
    assert policy.check(m) == "active"


# 功能：check 在 expires_at 已过时返回 expired
# 设计：注入 now_fn 固定为 2026-06-01，构造 expires_at=2026-01-01 → expired
def test_check_past_expires_at_is_expired() -> None:
    fixed = datetime(2026, 6, 1, tzinfo=timezone.utc)
    policy = MemoryExpiryPolicy(now_fn=lambda: fixed)
    m = MemoryItem(
        id="m-1", content="x", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z",
        expires_at="2026-01-01T00:00:00Z",
    )
    assert policy.check(m) == "expired"


# 功能：archive_expired 自动把过期记忆 status 改为 archived
# 设计：写 2 条到 LocalMemoryBackend（1 过期 / 1 永久），断言 archive 后只过期那条变 archived
@pytest.mark.asyncio
async def test_archive_expired_marks_status_archived(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    expired = MemoryItem(
        id="m-1", content="old", memory_type="user", importance=0.5,
        status="active", created_at="2020-01-01T00:00:00Z",
        expires_at="2020-12-31T00:00:00Z",
    )
    permanent = MemoryItem(
        id="m-2", content="forever", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z", expires_at=None,
    )
    await backend.write(expired)
    await backend.write(permanent)
    policy = MemoryExpiryPolicy()
    count = await policy.archive_expired(backend)
    assert count == 1
    m1 = await backend.read("m-1")
    m2 = await backend.read("m-2")
    assert m1 is not None and m1.status == "archived"
    assert m2 is not None and m2.status == "active"


# 功能：archive_expired 已 archived 的不重复处理
# 设计：手动写入 status=archived + expires_at 已过，archive 后 count=0
@pytest.mark.asyncio
async def test_archive_expired_skips_already_archived(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    await backend.write(MemoryItem(
        id="m-1", content="x", memory_type="user", importance=0.5,
        status="archived", created_at="2020-01-01T00:00:00Z",
        expires_at="2020-12-31T00:00:00Z",
    ))
    policy = MemoryExpiryPolicy()
    count = await policy.archive_expired(backend)
    assert count == 0


# 功能：archive_expired 同步写审计事件
# 设计：传入 audit_logger，断言 expire 事件落盘
@pytest.mark.asyncio
async def test_archive_expired_writes_audit_event(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")
    await backend.write(MemoryItem(
        id="m-1", content="x", memory_type="user", importance=0.5,
        status="active", created_at="2020-01-01T00:00:00Z",
        expires_at="2020-12-31T00:00:00Z",
    ))
    policy = MemoryExpiryPolicy()
    count = await policy.archive_expired(backend, audit_logger=audit)
    assert count == 1
    events = audit.query(memory_id="m-1")
    assert any(e.event_type == "expire" for e in events)


# 功能：to_archived 返回 status=archived 副本，原对象不变
# 设计：原对象 status 应保持 active
def test_to_archived_returns_copy_with_status_archived() -> None:
    policy = MemoryExpiryPolicy()
    m = MemoryItem(
        id="m-1", content="x", memory_type="user", importance=0.5,
        status="active", created_at="2026-01-01T00:00:00Z",
    )
    archived = policy.to_archived(m)
    assert archived.status == "archived"
    assert m.status == "active"  # 原对象不变


# 功能：to_archived 对已 archived 直接返回原对象
# 设计：避免无谓复制
def test_to_archived_idempotent_for_already_archived() -> None:
    policy = MemoryExpiryPolicy()
    m = MemoryItem(
        id="m-1", content="x", memory_type="user", importance=0.5,
        status="archived", created_at="2026-01-01T00:00:00Z",
    )
    out = policy.to_archived(m)
    assert out is m
