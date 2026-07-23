from __future__ import annotations

import json
from pathlib import Path

import pytest

from kivi_agent.core.memory.audit import MemoryAuditLogger, safe_path
from kivi_agent.core.memory.backend import MemoryAuditEvent


# 功能：append 把 MemoryAuditEvent 序列化为 JSON 写入文件
# 设计：append 后直接读 .jsonl 文本，断言包含 memory_id 与 event_type
def test_append_writes_jsonl_line(tmp_path: Path) -> None:
    log = MemoryAuditLogger(tmp_path / "audit.jsonl")
    evt = MemoryAuditEvent(
        memory_id="m-1", event_type="create",
        ts="2026-01-01T00:00:00Z", actor="user:u-1",
    )
    log.append(evt)
    text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert '"memory_id": "m-1"' in text
    assert '"event_type": "create"' in text


# 功能：query(memory_id=...) 仅返回匹配的事件
# 设计：写 3 条不同 id 的事件，断言 query 单 id 只返回那条
def test_query_by_memory_id_filters(tmp_path: Path) -> None:
    log = MemoryAuditLogger(tmp_path / "audit.jsonl")
    for mid in ("m-1", "m-2", "m-3"):
        log.append(MemoryAuditEvent(
            memory_id=mid, event_type="create",
            ts="2026-01-01T00:00:00Z", actor="user",
        ))
    results = log.query(memory_id="m-2")
    assert len(results) == 1
    assert results[0].memory_id == "m-2"


# 功能：query(since=...) 按 ts 前缀过滤
# 设计：写跨日事件，断言 since 限定当天
def test_query_since_filters_by_ts_prefix(tmp_path: Path) -> None:
    log = MemoryAuditLogger(tmp_path / "audit.jsonl")
    log.append(MemoryAuditEvent("m-1", "create", "2026-01-01T00:00:00Z", "u"))
    log.append(MemoryAuditEvent("m-2", "create", "2026-02-01T00:00:00Z", "u"))
    results = log.query(since="2026-02")
    assert len(results) == 1
    assert results[0].memory_id == "m-2"


# 功能：query 不存在的 memory_id 返回空列表
# 设计：边界条件
def test_query_no_match_returns_empty(tmp_path: Path) -> None:
    log = MemoryAuditLogger(tmp_path / "audit.jsonl")
    log.append(MemoryAuditEvent("m-1", "create", "2026-01-01T00:00:00Z", "u"))
    assert log.query(memory_id="nope") == []


# 功能：query 默认按 ts 升序返回
# 设计：乱序写入，断言 query 全量按 ts 排序
def test_query_orders_by_ts_ascending(tmp_path: Path) -> None:
    log = MemoryAuditLogger(tmp_path / "audit.jsonl")
    log.append(MemoryAuditEvent("m-1", "create", "2026-01-03T00:00:00Z", "u"))
    log.append(MemoryAuditEvent("m-2", "create", "2026-01-01T00:00:00Z", "u"))
    log.append(MemoryAuditEvent("m-3", "create", "2026-01-02T00:00:00Z", "u"))
    results = log.query()
    assert [e.memory_id for e in results] == ["m-2", "m-3", "m-1"]


# 功能：JSONL 落盘格式——每行一个完整 JSON
# 设计：append 2 次后按行读，断言每行都是合法 JSON
def test_jsonl_persistence_format(tmp_path: Path) -> None:
    log = MemoryAuditLogger(tmp_path / "audit.jsonl")
    log.append(MemoryAuditEvent("m-1", "create", "2026-01-01T00:00:00Z", "u"))
    log.append(MemoryAuditEvent("m-2", "update", "2026-01-02T00:00:00Z", "u"))
    text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip()
    lines = text.split("\n")
    assert len(lines) == 2
    for line in lines:
        data = json.loads(line)  # 必须是合法 JSON
        assert "memory_id" in data
        assert "event_type" in data
        assert "ts" in data
        assert "actor" in data


# 功能：path traversal 防护：safe_path 限制 target 必须在 base_dir 之下
# 设计：构造 ../escape.json 形式的相对越界路径，断言抛 ValueError
def test_safe_path_blocks_traversal(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    escape = base / ".." / "escape.json"
    with pytest.raises(ValueError):
        safe_path(base, escape)


# 功能：safe_path 接受 base_dir 之内的合法目标
# 设计：正常路径应当原样返回
def test_safe_path_allows_inside(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    target = base / "inside.json"
    resolved = safe_path(base, target)
    assert resolved == target.resolve()


# 功能：record 是 append 的异步包装
# 设计：await record(event) 后断言文件已写入
@pytest.mark.asyncio
async def test_async_record_writes_event(tmp_path: Path) -> None:
    log = MemoryAuditLogger(tmp_path / "audit.jsonl")
    await log.record(MemoryAuditEvent("m-1", "create", "2026-01-01T00:00:00Z", "u"))
    text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "m-1" in text


# 功能：query_range(start, end) 返回窗口内事件
# 设计：构造 3 个 ts，断言 start..end 区间过滤
def test_query_range_filters_by_window(tmp_path: Path) -> None:
    log = MemoryAuditLogger(tmp_path / "audit.jsonl")
    log.append(MemoryAuditEvent("m-1", "create", "2026-01-01T00:00:00Z", "u"))
    log.append(MemoryAuditEvent("m-2", "create", "2026-01-15T00:00:00Z", "u"))
    log.append(MemoryAuditEvent("m-3", "create", "2026-02-01T00:00:00Z", "u"))
    results = log.query_range("2026-01-10T00:00:00Z", "2026-01-31T23:59:59Z")
    assert [e.memory_id for e in results] == ["m-2"]


# 功能：log_create 便捷方法自动填 ts 并落盘
# 设计：调用后 query(memory_id) 能拿到
def test_log_create_helper(tmp_path: Path) -> None:
    log = MemoryAuditLogger(tmp_path / "audit.jsonl")
    log.log_create("m-1")
    results = log.query(memory_id="m-1")
    assert len(results) == 1
    assert results[0].event_type == "create"
    assert results[0].actor == "system:audit"


# 功能：多 append 累积为多行
# 设计：append N 次后断言行数 = N
def test_multiple_appends_accumulate(tmp_path: Path) -> None:
    log = MemoryAuditLogger(tmp_path / "audit.jsonl")
    for i in range(5):
        log.append(MemoryAuditEvent(f"m-{i}", "create", "2026-01-01T00:00:00Z", "u"))
    text = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip()
    assert len(text.split("\n")) == 5
