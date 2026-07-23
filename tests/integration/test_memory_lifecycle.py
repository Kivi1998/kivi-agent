"""记忆生命周期端到端集成测试（Wave 6.1 J2）。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from kivi_agent.core.memory.audit import MemoryAuditLogger
from kivi_agent.core.memory.backend import MemoryAuditEvent, MemoryItem
from kivi_agent.core.memory.expire import MemoryExpiryPolicy
from kivi_agent.core.memory.fallback import MemoryExtractionFallback
from kivi_agent.core.memory.filter import SensitiveInfoFilter
from kivi_agent.core.memory.lifecycle import MemoryLifecycle, build_default_lifecycle


# Mock backend：支持 list_all、write、read、update、delete、search、audit。
class MockMemoryBackend:
    """端到端测试用的内存 backend。"""

    def __init__(self) -> None:
        self.items: dict[str, MemoryItem] = {}
        self.audit_log: list[MemoryAuditEvent] = []

    async def write(self, memory: MemoryItem) -> str:
        self.items[memory.id] = memory
        return memory.id

    async def read(self, memory_id: str) -> MemoryItem | None:
        return self.items.get(memory_id)

    async def search(self, query: str, top_k: int = 5) -> list[MemoryItem]:
        if not query:
            return list(self.items.values())[:top_k]
        results = [m for m in self.items.values() if query in m.content]
        return results[:top_k]

    async def update(self, memory_id: str, memory: MemoryItem) -> None:
        self.items[memory_id] = memory

    async def delete(self, memory_id: str) -> None:
        self.items.pop(memory_id, None)

    async def audit(self, event: MemoryAuditEvent) -> None:
        self.audit_log.append(event)

    async def list_all(self) -> list[MemoryItem]:
        return list(self.items.values())


# 测试用 embedding fn：完全相同文本 → 完全相同向量（sha256 哈希保证跨进程稳定）。
# 用 16 维降低随机冲突概率（2 维下不同文本 cosine 也可能 > 0.95）。
def _deterministic_embed(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode()).hexdigest()
    return [int(digest[i : i + 2], 16) / 255.0 for i in range(0, 32, 2)]


# 功能：端到端——filter→dedup→write→audit→expire 全链路
# 设计：构造 3 条记忆（1 敏感信息 / 1 重复 / 1 过期），依次走完整流程
@pytest.mark.asyncio
async def test_e2e_filter_dedup_write_audit_expire(tmp_path: Path) -> None:
    backend = MockMemoryBackend()
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")
    expiry = MemoryExpiryPolicy(
        now_fn=lambda: datetime(2026, 12, 1, tzinfo=UTC),
    )
    lc = MemoryLifecycle(
        filter=SensitiveInfoFilter(),
        embedding_fn=_deterministic_embed,
        expiry_policy=expiry,
    )

    # 1) 写入一条新记忆（含敏感信息）
    new_item = MemoryItem(
        id="m-1", content="password=hunter2 user prefers dark mode",
        memory_type="user", importance=0.5, status="active",
        created_at="2026-01-01T00:00:00Z", expires_at=None,
    )
    res1 = await lc.process(new_item, backend, audit)
    assert res1["action"] == "added"
    assert res1["memory_id"] == "m-1"
    assert any("credential" in w for w in res1["warnings"])
    # 验证：写入的 content 已被脱敏
    stored = await backend.read("m-1")
    assert stored is not None
    assert "hunter2" not in stored.content

    # 2) 写入完全相同内容 → 触发 merge
    dup_item = MemoryItem(
        id="m-2", content="password=hunter2 user prefers dark mode",
        memory_type="user", importance=0.7, status="active",
        created_at="2026-06-01T00:00:00Z", expires_at=None,
    )
    res2 = await lc.process(dup_item, backend, audit)
    assert res2["action"] == "merged"
    assert res2["memory_id"] == "m-1"

    # 3) 写入无关内容 → add
    new2 = MemoryItem(
        id="m-3", content="user likes cats and coffee",
        memory_type="user", importance=0.5, status="active",
        created_at="2026-02-01T00:00:00Z", expires_at=None,
    )
    res3 = await lc.process(new2, backend, audit)
    assert res3["action"] == "added"

    # 4) 写入一条已过期的记忆，触发 expire → archive
    expired = MemoryItem(
        id="m-4", content="old fact about project",
        memory_type="project", importance=0.3, status="active",
        created_at="2020-01-01T00:00:00Z",
        expires_at="2020-12-31T00:00:00Z",
    )
    res4 = await lc.process(expired, backend, audit)
    assert res4["action"] == "added"
    # 现在跑过期扫描
    archived_count = await expiry.archive_expired(backend, audit_logger=audit)
    assert archived_count == 1
    m4 = await backend.read("m-4")
    assert m4 is not None
    assert m4.status == "archived"

    # 5) 审计：4 条记忆各有 create 事件 + 1 条 expire 事件
    events = audit.query()
    types = [e.event_type for e in events]
    assert types.count("create") >= 3
    assert types.count("expire") == 1


# 功能：端到端——重复内容在 add 后再写入会合并，并保留较新的 importance
# 设计：构造两条 importance 不同的"相同"记忆，验证合并后的 importance 取最大值
@pytest.mark.asyncio
async def test_e2e_merge_keeps_higher_importance(tmp_path: Path) -> None:
    backend = MockMemoryBackend()
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")
    lc = MemoryLifecycle(embedding_fn=_deterministic_embed)

    await lc.process(MemoryItem(
        id="m-1", content="shared content", memory_type="user",
        importance=0.3, status="active", created_at="2026-01-01T00:00:00Z",
    ), backend, audit)

    await lc.process(MemoryItem(
        id="m-2", content="shared content", memory_type="user",
        importance=0.9, status="active", created_at="2026-06-01T00:00:00Z",
    ), backend, audit)

    # m-1 的 importance 应被提升到 0.9
    m1 = await backend.read("m-1")
    assert m1 is not None
    assert m1.importance == 0.9


# 功能：端到端——fallback 保护主任务不受提取失败影响
# 设计：构造一个会抛异常的 extractor，验证主任务继续 + 返回 ok=False
@pytest.mark.asyncio
async def test_e2e_fallback_keeps_main_task_alive(tmp_path: Path) -> None:
    backend = MockMemoryBackend()
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")
    lc = build_default_lifecycle()
    fb = MemoryExtractionFallback()

    # 模拟提取器抛异常
    async def broken_extractor() -> list[MemoryItem]:
        raise RuntimeError("LLM unreachable")

    result = await fb.safe_extract(broken_extractor)
    assert result["ok"] is False
    assert result["items"] == []
    assert "LLM unreachable" in result["error"]

    # 主任务继续：仍然能写入一条记忆
    res = await lc.process(MemoryItem(
        id="m-1", content="after extraction failure", memory_type="user",
        importance=0.5, status="active", created_at="2026-01-01T00:00:00Z",
    ), backend, audit)
    assert res["action"] == "added"


# 功能：端到端——多 memory_type 共存
# 设计：写入 user/feedback/project/reference/task 各一条，验证全部 added
@pytest.mark.asyncio
async def test_e2e_multiple_memory_types(tmp_path: Path) -> None:
    backend = MockMemoryBackend()
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")
    lc = build_default_lifecycle()  # 无 dedup

    types = ["user", "feedback", "project", "reference", "task"]
    for i, mtype in enumerate(types):
        res = await lc.process(MemoryItem(
            id=f"m-{i}", content=f"content {i} for {mtype}",
            memory_type=mtype, importance=0.5, status="active",
            created_at="2026-01-01T00:00:00Z",
        ), backend, audit)
        assert res["action"] == "added"

    assert len(backend.items) == 5


# 功能：端到端——filter 命中后写审计事件记录 create（仍走审计）
# 设计：含敏感词的记忆写入后审计中有 create 事件
@pytest.mark.asyncio
async def test_e2e_filtered_content_still_audited(tmp_path: Path) -> None:
    backend = MockMemoryBackend()
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")
    lc = build_default_lifecycle()
    res = await lc.process(MemoryItem(
        id="m-1", content="api_key=sk-abc contact me",
        memory_type="user", importance=0.5, status="active",
        created_at="2026-01-01T00:00:00Z",
    ), backend, audit)
    assert res["action"] == "added"
    events = audit.query(memory_id="m-1")
    assert len(events) == 1
    assert events[0].event_type == "create"


# 功能：端到端——批量写入 10 条全部成功（不相互影响）
# 设计：构造 10 条不同内容的记忆，验证全部 added
@pytest.mark.asyncio
async def test_e2e_batch_writes(tmp_path: Path) -> None:
    backend = MockMemoryBackend()
    audit = MemoryAuditLogger(tmp_path / "audit.jsonl")
    lc = build_default_lifecycle()
    for i in range(10):
        res = await lc.process(MemoryItem(
            id=f"m-{i}", content=f"unique content number {i} xyz",
            memory_type="user", importance=0.5, status="active",
            created_at="2026-01-01T00:00:00Z",
        ), backend, audit)
        assert res["action"] == "added"
    assert len(backend.items) == 10
    events = audit.query()
    assert len(events) == 10
