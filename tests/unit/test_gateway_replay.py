"""WT-E1: EventReplayBuffer 单元测试（agent: package-web-gateway-v3）。

设计：
- 纯同步单元测试（不依赖 asyncio / 异步运行时），覆盖 push / since / clear / 上限
- 上限测试：max_size=3 时推 5 条应保留最后 3 条
- since 测试：since_ts 为空返回全部 / since_ts=某值返回 ts > since_ts 的事件
- 多 session 桶隔离测试
"""

from __future__ import annotations

import pytest

from kivi_agent.gateway.replay import DEFAULT_MAX_SIZE, EventReplayBuffer


# 功能：push 后 since 包含已 push 的事件
# 设计：推 3 条不同 ts 事件，since("", "") 返回全部 3 条
def test_replay_push_and_since_returns_all_when_empty_ts() -> None:
    buf = EventReplayBuffer()
    buf.push("sess-1", {"type": "x", "ts": "2026-01-01T00:00:00Z"})
    buf.push("sess-1", {"type": "x", "ts": "2026-01-01T00:00:01Z"})
    buf.push("sess-1", {"type": "x", "ts": "2026-01-01T00:00:02Z"})

    result = buf.since("sess-1", "")
    assert len(result) == 3
    assert [r["ts"] for r in result] == [
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:01Z",
        "2026-01-01T00:00:02Z",
    ]


# 功能：since(since_ts) 只返回 ts > since_ts 的事件（ISO 8601 字典序比较）
# 设计：推 5 条不同 ts 事件，since(_, "t2") 返回 ts > t2 的 2 条
def test_replay_since_filters_by_ts_greater_than() -> None:
    buf = EventReplayBuffer()
    for i in range(5):
        buf.push("sess-1", {"type": "x", "ts": f"2026-01-01T00:00:0{i}"})

    # since_ts = t2 → 应返回 t3, t4
    result = buf.since("sess-1", "2026-01-01T00:00:02")
    assert len(result) == 2
    assert [r["ts"] for r in result] == [
        "2026-01-01T00:00:03",
        "2026-01-01T00:00:04",
    ]


# 功能：max_size 限制生效：超长时丢最早（FIFO）
# 设计：max_size=3 推 5 条，断言保留最后 3 条且最早 2 条被丢弃
def test_replay_respects_max_size_fifo() -> None:
    buf = EventReplayBuffer(max_size=3)
    for i in range(5):
        buf.push("sess-1", {"type": "x", "ts": f"t{i}"})

    result = buf.since("sess-1", "")
    assert len(result) == 3
    assert [r["ts"] for r in result] == ["t2", "t3", "t4"]


# 功能：不同 session 桶彼此隔离（按 session_id 分桶）
# 设计：sess-1 / sess-2 各推 2 条，since(sess-1) 只返回 sess-1 的 2 条
def test_replay_isolates_per_session_buckets() -> None:
    buf = EventReplayBuffer()
    buf.push("sess-1", {"type": "a", "ts": "t1"})
    buf.push("sess-1", {"type": "a", "ts": "t2"})
    buf.push("sess-2", {"type": "b", "ts": "t3"})
    buf.push("sess-2", {"type": "b", "ts": "t4"})

    r1 = buf.since("sess-1", "")
    r2 = buf.since("sess-2", "")
    assert len(r1) == 2
    assert len(r2) == 2
    assert all(ev["ts"] in {"t1", "t2"} for ev in r1)
    assert all(ev["ts"] in {"t3", "t4"} for ev in r2)
    # sessions() 返回所有 session_id
    assert set(buf.sessions()) == {"sess-1", "sess-2"}


# 功能：未 push 过的 session 调 since 返回空 list
# 设计：推 sess-1 后调 since("sess-unknown", "")
def test_replay_since_unknown_session_returns_empty() -> None:
    buf = EventReplayBuffer()
    buf.push("sess-1", {"type": "x", "ts": "t1"})
    assert buf.since("sess-unknown", "") == []


# 功能：clear 删除指定 session 桶；clear_all 清空全部
# 设计：推 2 个 session → clear(sess-1) → since(sess-1) 为空；since(sess-2) 仍正常
def test_replay_clear_session_and_clear_all() -> None:
    buf = EventReplayBuffer()
    buf.push("sess-1", {"type": "x", "ts": "t1"})
    buf.push("sess-2", {"type": "x", "ts": "t2"})

    buf.clear("sess-1")
    assert buf.since("sess-1", "") == []
    assert len(buf.since("sess-2", "")) == 1
    assert buf.sessions() == ["sess-2"]

    buf.clear_all()
    assert buf.sessions() == []
    assert buf.since("sess-2", "") == []


# 功能：max_size <= 0 抛 ValueError（构造期校验）
# 设计：直接调 EventReplayBuffer(0) 断言 ValueError
def test_replay_rejects_non_positive_max_size() -> None:
    with pytest.raises(ValueError):
        EventReplayBuffer(max_size=0)
    with pytest.raises(ValueError):
        EventReplayBuffer(max_size=-1)


# 功能：默认 max_size 是 100（与 v1 §5.2.1 契约一致）
# 设计：推 105 条，断言保留 100 条且是最新的 100 条
def test_replay_default_max_size_is_100() -> None:
    buf = EventReplayBuffer()
    assert buf.max_size == DEFAULT_MAX_SIZE
    assert DEFAULT_MAX_SIZE == 100
    for i in range(105):
        buf.push("sess-1", {"type": "x", "ts": f"t{i}"})
    result = buf.since("sess-1", "")
    assert len(result) == 100
    # 保留的是 t5..t104（最新的 100 条）
    assert result[0]["ts"] == "t5"
    assert result[-1]["ts"] == "t104"


# 功能：空 session_id 的事件不入桶（防御性）
# 设计：push("", {...}) 后 sessions() 为空 + len(buf) == 0
def test_replay_empty_session_id_dropped() -> None:
    buf = EventReplayBuffer()
    buf.push("", {"type": "x", "ts": "t1"})
    assert buf.sessions() == []
    assert len(buf) == 0
