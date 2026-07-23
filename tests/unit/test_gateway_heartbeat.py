"""WT-E1: HeartbeatEmitter 单元测试（agent: package-web-gateway-v3）。

设计：
- 用 FakeEventBus 收集 ping 事件
- 用 asyncio.sleep + Event.wait() 模式自然推进时间（interval 调小为 0.1s 便于测试）
- 验证：start/stop 生命周期 + add/remove session 行为 + 周期性 ping
"""

from __future__ import annotations

import asyncio

from kivi_agent.gateway.heartbeat import HeartbeatEmitter
from tests._fakes.event_bus import FakeEventBus


# 功能：start 后每 interval_s 给每个 active session 发 1 条 ping
# 设计：interval 调 0.1s，加 2 session，等 0.3s 后断言发了 ≥4 条（2 sessions × 2 ticks）
async def test_heartbeat_pings_each_active_session_periodically() -> None:
    bus = FakeEventBus()
    emitter = HeartbeatEmitter(bus=bus, interval_s=0.1)
    emitter.add_session("sess-1")
    emitter.add_session("sess-2")
    emitter.start()
    try:
        await asyncio.sleep(0.3)
    finally:
        await emitter.stop()

    # 至少 4 条 ping（保守下限：避免 CI 抖动）
    ping_events = [e for e in bus.events if getattr(e, "type", "") == "ping"]
    assert len(ping_events) >= 4
    # ping_count 与 bus.events 计数一致
    assert emitter.ping_count == len(ping_events)
    # 每个 session 至少 2 条（2 ticks）
    sess_counts: dict[str, int] = {}
    for ev in ping_events:
        sid = getattr(ev, "session_id", None)
        if isinstance(sid, str):
            sess_counts[sid] = sess_counts.get(sid, 0) + 1
    assert sess_counts.get("sess-1", 0) >= 2
    assert sess_counts.get("sess-2", 0) >= 2


# 功能：没有 active session 时不发 ping（不浪费资源）
# 设计：不加 session 就 start，等 0.3s 后断言 0 条 ping
async def test_heartbeat_no_ping_without_active_sessions() -> None:
    bus = FakeEventBus()
    emitter = HeartbeatEmitter(bus=bus, interval_s=0.1)
    emitter.start()
    try:
        await asyncio.sleep(0.3)
    finally:
        await emitter.stop()

    ping_events = [e for e in bus.events if getattr(e, "type", "") == "ping"]
    assert len(ping_events) == 0
    assert emitter.ping_count == 0


# 功能：add_session / remove_session 动态调整活跃列表
# 设计：add → 等 ping 出现 → remove → 再等 → 新 ping 不再带已 remove 的 session
async def test_heartbeat_add_remove_session_dynamically() -> None:
    bus = FakeEventBus()
    emitter = HeartbeatEmitter(bus=bus, interval_s=0.1)
    emitter.add_session("sess-A")
    emitter.start()
    try:
        # 等 1 个 tick 让 sess-A 收到 ping
        await asyncio.sleep(0.15)
        # remove sess-A
        emitter.remove_session("sess-A")
        assert emitter.active_session_count() == 0
        # 再等 0.3s，新 ping 不应有 sess-A
        before = sum(
            1
            for e in bus.events
            if getattr(e, "type", "") == "ping"
            and getattr(e, "session_id", None) == "sess-A"
        )
        await asyncio.sleep(0.3)
        after = sum(
            1
            for e in bus.events
            if getattr(e, "type", "") == "ping"
            and getattr(e, "session_id", None) == "sess-A"
        )
        # remove 后不应再产生 sess-A 的 ping
        assert after == before
    finally:
        await emitter.stop()


# 功能：stop() 后 task 立即取消，ping 立即停止
# 设计：start + add session → 等到至少 1 个 ping → stop → 立刻断言新 ping 不再产生
async def test_heartbeat_stop_cancels_task_immediately() -> None:
    bus = FakeEventBus()
    emitter = HeartbeatEmitter(bus=bus, interval_s=0.1)
    emitter.add_session("sess-1")
    emitter.start()
    try:
        await asyncio.sleep(0.15)
    finally:
        await emitter.stop()

    # stop 后 count 立即定格
    count_at_stop = emitter.ping_count
    # 再等 0.3s，count 不再增长
    await asyncio.sleep(0.3)
    assert emitter.ping_count == count_at_stop


# 功能：重复 start() 幂等，不会启动多个 task
# 设计：start 3 次，断言 task 引用只 1 个（async 因为 create_task 需要 running loop）
async def test_heartbeat_start_is_idempotent() -> None:
    bus = FakeEventBus()
    emitter = HeartbeatEmitter(bus=bus, interval_s=0.1)
    emitter.start()
    task1 = emitter._task
    emitter.start()
    task2 = emitter._task
    assert task1 is task2  # 同一 task 引用
    # cleanup
    await emitter.stop()


# 功能：ping 事件带 ts 字段（ISO 8601）
# 设计：发 1 个 ping 后断言 ts 是字符串且非空
async def test_heartbeat_ping_event_has_iso_ts() -> None:
    bus = FakeEventBus()
    emitter = HeartbeatEmitter(bus=bus, interval_s=0.05)
    emitter.add_session("sess-1")
    emitter.start()
    try:
        await asyncio.sleep(0.1)
    finally:
        await emitter.stop()

    pings = [e for e in bus.events if getattr(e, "type", "") == "ping"]
    assert len(pings) >= 1
    first = pings[0]
    ts = getattr(first, "ts", "")
    assert isinstance(ts, str)
    assert len(ts) > 0
