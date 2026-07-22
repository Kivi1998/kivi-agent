from __future__ import annotations

from pathlib import Path

import pytest

from kivi_agent.core.memory.backend import MemoryAuditEvent, MemoryItem
from kivi_agent.core.memory.local_backend import LocalMemoryBackend


# 功能：write → read 闭环：写入的 MemoryItem 能按 id 完整读出
# 设计：写入一条完整字段的 MemoryItem，read 拿回后断言 7 字段全部一致；这是 6 方法的最小 happy path
@pytest.mark.asyncio
async def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    item = MemoryItem(
        id="m-1",
        content="hello world",
        memory_type="user",
        importance=0.8,
        status="active",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2027-01-01T00:00:00Z",
    )
    mid = await backend.write(item)
    assert mid == "m-1"

    got = await backend.read(mid)
    assert got is not None
    assert got.id == item.id
    assert got.content == item.content
    assert got.memory_type == item.memory_type
    assert got.importance == item.importance
    assert got.status == item.status
    assert got.created_at == item.created_at
    assert got.expires_at == item.expires_at


# 功能：read 不存在的 id 返回 None
# 设计：直接 read 不存在的 id，断言返回 None 而非抛异常
@pytest.mark.asyncio
async def test_read_nonexistent_returns_none(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    got = await backend.read("nope")
    assert got is None


# 功能：search 按 query 在 content 中做子串匹配（Markdown 全文搜索作为向量召回占位）
# 设计：写入 3 条不同 content 的记忆，搜 "alpha" 只返回 1 条；这是 v1 §T4"Markdown 全文检索"占位实现
@pytest.mark.asyncio
async def test_search_matches_substring_in_content(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    for i, content in enumerate(["alpha bravo", "charlie delta", "echo alpha"]):
        await backend.write(
            MemoryItem(
                id=f"m-{i}",
                content=content,
                memory_type="user",
                importance=0.5,
                status="active",
                created_at="2026-01-01T00:00:00Z",
            )
        )
    results = await backend.search("alpha")
    ids = sorted(r.id for r in results)
    assert ids == ["m-0", "m-2"]


# 功能：search 的 top_k 参数限制返回条数
# 设计：写入 5 条都包含 "x" 的记忆，search top_k=2 断言只返回 2 条；
#      这是 v1 §T3 表格 search(top_k=5) 默认值的契约基础
@pytest.mark.asyncio
async def test_search_respects_top_k(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    for i in range(5):
        await backend.write(
            MemoryItem(
                id=f"m-{i}",
                content=f"x item {i}",
                memory_type="user",
                importance=0.5,
                status="active",
                created_at="2026-01-01T00:00:00Z",
            )
        )
    results = await backend.search("x", top_k=2)
    assert len(results) == 2


# 功能：search 空 query 返回空列表
# 设计：search("") 断言返回 []，避免空查询把所有记忆返回出来
@pytest.mark.asyncio
async def test_search_empty_query_returns_empty(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    await backend.write(
        MemoryItem(
            id="m-1",
            content="x",
            memory_type="user",
            importance=0.5,
            status="active",
            created_at="2026-01-01T00:00:00Z",
        )
    )
    results = await backend.search("")
    assert results == []


# 功能：update 能覆盖已有记忆的全部字段
# 设计：write 一条，更新字段后 read 拿回，断言字段值已更新
@pytest.mark.asyncio
async def test_update_overwrites_fields(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    original = MemoryItem(
        id="m-1",
        content="old",
        memory_type="user",
        importance=0.5,
        status="active",
        created_at="2026-01-01T00:00:00Z",
    )
    await backend.write(original)

    updated = MemoryItem(
        id="m-1",
        content="new content",
        memory_type="feedback",
        importance=0.9,
        status="archived",
        created_at="2026-01-01T00:00:00Z",
        expires_at="2027-01-01T00:00:00Z",
    )
    await backend.update("m-1", updated)

    got = await backend.read("m-1")
    assert got is not None
    assert got.content == "new content"
    assert got.memory_type == "feedback"
    assert got.importance == 0.9
    assert got.status == "archived"
    assert got.expires_at == "2027-01-01T00:00:00Z"


# 功能：delete 后 read 返回 None
# 设计：write + delete + read 闭环验证；这是 6 方法完整 round-trip
@pytest.mark.asyncio
async def test_delete_removes_entry(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    await backend.write(
        MemoryItem(
            id="m-1",
            content="x",
            memory_type="user",
            importance=0.5,
            status="active",
            created_at="2026-01-01T00:00:00Z",
        )
    )
    await backend.delete("m-1")
    assert await backend.read("m-1") is None


# 功能：delete 不存在的 id 是幂等操作（不抛异常）
# 设计：delete 一个不存在的 id，断言不抛；这是协议层"delete 必须幂等"的基本契约
@pytest.mark.asyncio
async def test_delete_nonexistent_is_idempotent(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    await backend.delete("nope")  # 不应抛异常


# 功能：audit 把事件追加到 audit.log（事件溯源基础）
# 设计：写一条 audit 事件，断言 audit.log 文件存在且包含事件标识
@pytest.mark.asyncio
async def test_audit_writes_event_to_file(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    evt = MemoryAuditEvent(
        memory_id="m-1",
        event_type="create",
        ts="2026-01-01T00:00:00Z",
        actor="user:u-1",
    )
    await backend.audit(evt)
    log = tmp_path / "audit.log"
    assert log.exists()
    text = log.read_text(encoding="utf-8")
    assert "m-1" in text
    assert "create" in text
    assert "user:u-1" in text


# 功能：frontmatter 包含 4 个 v1 字段（memory_type / importance / status / expires_at）
# 设计：write 一条带 4 字段的记忆，读 markdown 文件直接解析 frontmatter；
#      这是 v1 §T4 + C §6.2 + §6.6 的 frontmatter 契约基础
@pytest.mark.asyncio
async def test_frontmatter_contains_v1_fields(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    await backend.write(
        MemoryItem(
            id="m-1",
            content="body text",
            memory_type="feedback",
            importance=0.7,
            status="active",
            created_at="2026-01-01T00:00:00Z",
            expires_at="2027-01-01T00:00:00Z",
        )
    )
    md_file = tmp_path / "m-1.md"
    text = md_file.read_text(encoding="utf-8")
    assert "memory_type: feedback" in text
    assert "importance: 0.7" in text
    assert "status: active" in text
    assert "expires_at: 2027-01-01T00:00:00Z" in text
    assert "body text" in text


# 功能：expires_at=None（永久记忆）时 frontmatter 写入 expires_at: never
# 设计：构造 expires_at=None 的记忆写入，断言 frontmatter 是 "never" 字符串而非空；
#      这是 C §6.6 永久记忆的可读约定
@pytest.mark.asyncio
async def test_frontmatter_expires_at_none_means_never(tmp_path: Path) -> None:
    backend = LocalMemoryBackend(root=tmp_path)
    await backend.write(
        MemoryItem(
            id="m-1",
            content="x",
            memory_type="user",
            importance=0.5,
            status="active",
            created_at="2026-01-01T00:00:00Z",
            expires_at=None,
        )
    )
    text = (tmp_path / "m-1.md").read_text(encoding="utf-8")
    assert "expires_at: never" in text


# 功能：LocalMemoryBackend 默认 root 路径为 ~/.kivi/memory/（工程重命名后）
# 设计：检查默认 root 是 ~/.kivi/memory 而非旧名 ~/.kama/memory；这是 v1 §T4 的命名约束
def test_default_root_is_kivi_memory() -> None:
    backend = LocalMemoryBackend()
    assert backend.root == Path("~/.kivi/memory").expanduser()


# 功能：LocalMemoryBackend 满足 MemoryBackend Protocol（结构子类型）
# 设计：isinstance 校验通过，确保满足 6 方法契约
def test_satisfies_memory_backend_protocol(tmp_path: Path) -> None:
    from kivi_agent.core.memory.backend import MemoryBackend

    backend = LocalMemoryBackend(root=tmp_path)
    assert isinstance(backend, MemoryBackend)
