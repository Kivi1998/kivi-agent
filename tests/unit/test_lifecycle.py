from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from kivi_agent.core.memory.audit import MemoryAuditLogger
from kivi_agent.core.memory.backend import MemoryItem
from kivi_agent.core.memory.filter import SensitiveInfoFilter
from kivi_agent.core.memory.lifecycle import MemoryLifecycle, build_default_lifecycle
from kivi_agent.core.memory.local_backend import LocalMemoryBackend


# 测试用 hash embedding：与 dedup 测试一致。
def _hash_embed(text: str) -> list[float]:
    # 用 hashlib 确定性 hash，避免 Python 内置 hash() 受 PYTHONHASHSEED 影响（导致跨进程 flaky）
    h = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "big")
    return [((h >> i) & 0xFF) / 255.0 for i in range(0, 32, 8)]


def _make_item(
    id: str, content: str, memory_type: str = "user",
    importance: float = 0.5, status: str = "active",
    expires_at: str | None = None,
) -> MemoryItem:
    return MemoryItem(
        id=id, content=content, memory_type=memory_type,
        importance=importance, status=status,
        created_at="2026-01-01T00:00:00Z", expires_at=expires_at,
    )


# 功能：build_default_lifecycle 不带 embedding_fn 时也能构造
# 设计：无 dedup 阶段不报错
def test_build_default_lifecycle_without_embedding() -> None:
    lc = build_default_lifecycle()
    assert lc.filter is not None
    assert lc.deduplicator is None
    assert lc.expiry is not None


# 功能：build_default_lifecycle 带 embedding_fn 时启用 dedup
# 设计：注入 fn，断言 deduplicator 不为 None
def test_build_default_lifecycle_with_embedding() -> None:
    lc = build_default_lifecycle(embedding_fn=_hash_embed)
    assert lc.deduplicator is not None


# 功能：filter→write 链：含敏感信息的记忆写入后是 sanitized 版本
# 设计：构造 content 含 password=xxx 的记忆，process 后从 backend 读出断言已脱敏
@pytest.mark.asyncio
async def test_process_filter_then_write_sanitizes_content(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")
    lc = MemoryLifecycle(filter=SensitiveInfoFilter())
    item = _make_item("m-1", "user password=hunter2 please remember")
    result = await lc.process(item, backend, audit)
    assert result["action"] == "added"
    stored = await backend.read("m-1")
    assert stored is not None
    assert "hunter2" not in stored.content
    assert "***REDACTED***" in stored.content
    assert any("credential" in w for w in result["warnings"])


# 功能：filter→dedup→write 链：完全相同文本触发 merge
# 设计：先写入 e1，再 process 相同内容的 n，断言 action=merged
@pytest.mark.asyncio
async def test_process_dedup_triggers_merge(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")
    lc = MemoryLifecycle(embedding_fn=_hash_embed, dedup_threshold=0.95)
    await backend.write(_make_item("e1", "user prefers dark mode"))
    result = await lc.process(
        _make_item("n", "user prefers dark mode"),
        backend, audit,
    )
    assert result["action"] == "merged"
    assert result["memory_id"] == "e1"


# 功能：filter→dedup→write 链：不相关文本触发 add
# 设计：先写入 e1（无关），再 process n，断言 action=added
@pytest.mark.asyncio
async def test_process_unrelated_text_adds(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")
    lc = MemoryLifecycle(embedding_fn=_hash_embed)
    await backend.write(_make_item("e1", "alpha bravo charlie delta"))
    result = await lc.process(
        _make_item("n", "echo foxtrot golf hotel"),
        backend, audit,
    )
    assert result["action"] == "added"
    stored = await backend.read("n")
    assert stored is not None


# 功能：process 后写审计事件
# 设计：写一条记忆，断言 audit.jsonl 中有 create 事件
@pytest.mark.asyncio
async def test_process_writes_audit_event(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")
    lc = MemoryLifecycle()
    result = await lc.process(_make_item("m-1", "hello"), backend, audit)
    assert result["action"] == "added"
    events = audit.query(memory_id="m-1")
    assert any(e.event_type == "create" for e in events)


# 功能：链上异常时降级——write 失败不抛
# 设计：构造一个 write 抛异常的 mock backend，断言 action=failed 且不抛
@pytest.mark.asyncio
async def test_process_handles_write_failure(tmp_path: Path) -> None:
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")

    class FailingBackend:
        async def list_all(self) -> list[MemoryItem]:
            return []
        async def write(self, memory: MemoryItem) -> str:
            raise OSError("disk full")
        async def read(self, memory_id: str) -> MemoryItem | None:
            return None
        async def search(self, query: str, top_k: int = 5) -> list[MemoryItem]:
            return []
        async def update(self, memory_id: str, memory: MemoryItem) -> None:
            pass
        async def delete(self, memory_id: str) -> None:
            pass
        async def audit(self, event: object) -> None:
            pass

    lc = MemoryLifecycle()
    result = await lc.process(_make_item("m-1", "x"), FailingBackend(), audit)  # type: ignore[arg-type]
    assert result["action"] == "failed"
    assert "write" in str(result["warnings"]).lower() or len(result["warnings"]) > 0


# 功能：链上异常时降级——list_all 失败跳过 dedup 走 add
# 设计：mock backend.list_all 抛异常，断言仍能写入
@pytest.mark.asyncio
async def test_process_handles_list_all_failure(tmp_path: Path) -> None:
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")

    class BrokenListAllBackend:
        def __init__(self) -> None:
            self.written: list[MemoryItem] = []

        async def list_all(self) -> list[MemoryItem]:
            raise RuntimeError("backend down")

        async def write(self, memory: MemoryItem) -> str:
            self.written.append(memory)
            return memory.id

        async def read(self, memory_id: str) -> MemoryItem | None:
            for m in self.written:
                if m.id == memory_id:
                    return m
            return None

        async def search(self, query: str, top_k: int = 5) -> list[MemoryItem]:
            return []

        async def update(self, memory_id: str, memory: MemoryItem) -> None:
            pass

        async def delete(self, memory_id: str) -> None:
            pass

        async def audit(self, event: object) -> None:
            pass

    lc = MemoryLifecycle(embedding_fn=_hash_embed)
    backend = BrokenListAllBackend()
    result = await lc.process(_make_item("m-1", "hello"), backend, audit)  # type: ignore[arg-type]
    assert result["action"] == "added"
    assert any("dedup" in w for w in result["warnings"])


# 功能：dedup 失败时降级为 add
# 设计：构造一个会让 dedup 内部抛异常的 embedding_fn，断言 process 仍能写
@pytest.mark.asyncio
async def test_process_dedup_failure_falls_back_to_add(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")

    def bad_embed(text: str) -> list[float]:
        raise RuntimeError("embed crash")

    lc = MemoryLifecycle(embedding_fn=bad_embed)
    result = await lc.process(_make_item("m-1", "hello"), backend, audit)
    assert result["action"] == "added"
    assert any("dedup" in w for w in result["warnings"])


# 功能：ProcessResult 字段契约
# 设计：构造 ProcessResult 验证类型 + 字段
def test_process_result_shape() -> None:
    from kivi_agent.core.memory.lifecycle import ProcessResult
    pr: ProcessResult = ProcessResult(
        action="added", memory_id="m-1", warnings=[],
    )
    assert pr["action"] == "added"
    assert pr["memory_id"] == "m-1"
    assert pr["warnings"] == []


# 功能：build_default_lifecycle 接受 filter 注入
# 设计：自定义 filter 应被 lifecycle 使用
def test_build_default_lifecycle_uses_custom_filter() -> None:
    custom = SensitiveInfoFilter(redact_email=False)
    lc = build_default_lifecycle(filter=custom)
    assert lc.filter is custom
