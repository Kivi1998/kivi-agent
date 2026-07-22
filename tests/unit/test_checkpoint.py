from __future__ import annotations

from pathlib import Path

from kivi_agent.core.session.checkpoint import CheckpointData, CheckpointStore


# 功能：验证保存后能读回同一份检查点数据
# 设计：save 后立即 load，逐字段断言，覆盖最基本的往返正确性
def test_save_and_load_checkpoint(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path)
    data = CheckpointData(run_id="r1", step=3, status="running", message_count=7, ts="2026-07-21T00:00:00+00:00")
    store.save("s1", "r1", data)
    loaded = store.load("s1", "r1")
    assert loaded is not None
    assert loaded.step == 3
    assert loaded.status == "running"


# 功能：验证读取不存在的检查点返回 None 而不是抛异常
# 设计：直接 load 一个从未 save 过的 run_id，断言返回 None，
#      确保调用方（runner 启动时检查是否有可恢复检查点）不需要包一层 try/except
def test_load_missing_checkpoint_returns_none(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path)
    assert store.load("s1", "nonexistent") is None


# 功能：验证对同一 (sid, run_id) 多次 save 后只保留最新一份（覆盖语义）
# 设计：save 两次不同 step 的数据，断言 load 拿到的是后一次（最新），而不是追加式累积
def test_save_overwrites_previous(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path)
    store.save("s1", "r1", CheckpointData(run_id="r1", step=1, status="running", message_count=2, ts="t1"))
    store.save("s1", "r1", CheckpointData(run_id="r1", step=5, status="success", message_count=8, ts="t2"))
    loaded = store.load("s1", "r1")
    assert loaded is not None
    assert loaded.step == 5
    assert loaded.status == "success"
    assert loaded.message_count == 8
