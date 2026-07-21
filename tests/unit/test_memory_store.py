from __future__ import annotations

from pathlib import Path

from kama_claude.core.memory.store import MemoryEntry, MemoryStore


# 功能：验证写入一条记忆后，能在同一 store 实例里通过 list_all 读回
# 设计：写入一条 type="feedback" 的记忆，断言字段完整、frontmatter 解析正确
def test_write_and_list_memory(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    entry = MemoryEntry(name="prefer-uv", type="feedback", description="用户偏好 uv 而不是 pip", body="始终用 uv 管理依赖")
    store.write(entry)
    entries = store.list_all()
    assert len(entries) == 1
    assert entries[0].name == "prefer-uv"
    assert entries[0].type == "feedback"
    assert entries[0].body == "始终用 uv 管理依赖"


# 功能：验证写入同名记忆会覆盖旧内容而不是产生重复文件
# 设计：用同一个 name 写两次不同 body，断言最终只有一条记忆且内容是第二次写入的
def test_write_same_name_overwrites(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.write(MemoryEntry(name="dup", type="project", description="d1", body="first"))
    store.write(MemoryEntry(name="dup", type="project", description="d2", body="second"))
    entries = store.list_all()
    assert len(entries) == 1
    assert entries[0].body == "second"


# 功能：验证写入多类记忆（user/feedback/project/reference）能完整保留
# 设计：每种类型写一条，断言 list_all 返回 4 条且 type 字段正确
def test_multiple_types_are_preserved(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.write(MemoryEntry(name="u1", type="user", description="d", body="b1"))
    store.write(MemoryEntry(name="f1", type="feedback", description="d", body="b2"))
    store.write(MemoryEntry(name="p1", type="project", description="d", body="b3"))
    store.write(MemoryEntry(name="r1", type="reference", description="d", body="b4"))
    entries = store.list_all()
    assert len(entries) == 4
    types = {e.type for e in entries}
    assert types == {"user", "feedback", "project", "reference"}


# 功能：验证 list_all 在空目录返回空列表
# 设计：空 store 调用 list_all，断言返回 []，确保初次使用没有记忆时无副作用
def test_list_all_empty_returns_empty_list(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    assert store.list_all() == []


# 功能：验证 MEMORY.md 索引文件被自动维护
# 设计：写入一条记忆后断言根目录下 MEMORY.md 存在且包含该记忆的 name
def test_memory_index_file_is_maintained(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path)
    store.write(MemoryEntry(name="idx-test", type="project", description="desc", body="body"))
    index_path = tmp_path / "MEMORY.md"
    assert index_path.exists()
    content = index_path.read_text(encoding="utf-8")
    assert "idx-test" in content
