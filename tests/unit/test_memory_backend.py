from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pytest

from kivi_agent.core.memory.backend import MemoryAuditEvent, MemoryBackend, MemoryItem


# 功能：MemoryItem 数据类字段完整保留
# 设计：构造 7 字段全部非默认值的实例，断言字段值；这是 v1 §T3 + C §6.1 的字段契约
def test_memory_item_fields() -> None:
    item = MemoryItem(
        id="m-1",
        content="hello",
        memory_type="user",
        importance=0.8,
        status="active",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2027-01-01T00:00:00Z",
    )
    assert item.id == "m-1"
    assert item.content == "hello"
    assert item.memory_type == "user"
    assert item.importance == 0.8
    assert item.status == "active"
    assert item.created_at == "2026-01-01T00:00:00Z"
    assert item.expires_at == "2027-01-01T00:00:00Z"


# 功能：MemoryItem 默认值正确
# 设计：仅必填字段（id/content/memory_type/importance/status/created_at）构造，
#      断言 expires_at 默认 None（永久记忆）
def test_memory_item_defaults() -> None:
    item = MemoryItem(
        id="m-1",
        content="x",
        memory_type="feedback",
        importance=0.5,
        status="active",
        created_at="2026-01-01T00:00:00Z",
    )
    assert item.expires_at is None


# 功能：MemoryAuditEvent 数据类字段完整保留
# 设计：构造 4 字段实例，断言字段值（memory_id / event_type / ts / actor）
def test_memory_audit_event_fields() -> None:
    evt = MemoryAuditEvent(
        memory_id="m-1",
        event_type="create",
        ts="2026-01-01T00:00:00Z",
        actor="user:u-1",
    )
    assert evt.memory_id == "m-1"
    assert evt.event_type == "create"
    assert evt.ts == "2026-01-01T00:00:00Z"
    assert evt.actor == "user:u-1"


# 功能：MemoryBackend 是 typing.Protocol
# 设计：直接用 isinstance 检查 MemoryBackend 是否是 Protocol 的实例，
#      这是 v1 §T3 要求"用 typing.Protocol 定义"的契约基础
def test_memory_backend_is_protocol() -> None:
    assert issubclass(MemoryBackend, Protocol)


# 功能：实现 MemoryBackend 的具体类能被协议识别
# 设计：内联一个最小实现，断言 isinstance(MyBackend(), MemoryBackend)；
#      这是 C 阶段实现 VectorMemoryBackend 时的契约基础
def test_concrete_impl_satisfies_protocol() -> None:
    class MyBackend:
        async def write(self, memory: MemoryItem) -> str:
            return memory.id

        async def read(self, memory_id: str) -> MemoryItem | None:
            return None

        async def search(self, query: str, top_k: int = 5) -> list[MemoryItem]:
            return []

        async def update(self, memory_id: str, memory: MemoryItem) -> None:
            pass

        async def delete(self, memory_id: str) -> None:
            pass

        async def audit(self, event: MemoryAuditEvent) -> None:
            pass

    impl = MyBackend()
    assert isinstance(impl, MemoryBackend)


# 功能：缺少任一方法的"实现"不能被协议识别
# 设计：缺一个方法（update）来验证 Protocol 是结构性子类型；确保实现必须满足全部 6 方法
def test_impl_missing_method_fails_protocol() -> None:
    class IncompleteBackend:
        async def write(self, memory: MemoryItem) -> str:
            return memory.id

        async def read(self, memory_id: str) -> MemoryItem | None:
            return None

        async def search(self, query: str, top_k: int = 5) -> list[MemoryItem]:
            return []

        # 故意缺 update / delete / audit

    impl = IncompleteBackend()
    assert not isinstance(impl, MemoryBackend)


# 功能：MemoryBackend.search 默认 top_k 参数为 5
# 设计：通过 Protocol 的方法签名反射读取默认值；这是 v1 §T3 表格的"default"列
def test_search_default_top_k_is_5() -> None:
    import inspect

    sig = inspect.signature(MemoryBackend.search)
    assert sig.parameters["top_k"].default == 5
