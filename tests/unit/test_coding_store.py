"""CodingResultStore 单元测试（WT-H3 / agent: package-dashboard-api-v52）。

测试目标：
1. JSONL 追加写 + iter_all 读取一致
2. list_runs 按 started_at 倒序去重
3. get_run 按 run_id 过滤
4. 路径遍历保护：拒绝 `..` 段 / `..` in run_id
5. save_batch 批量写入
6. iterations 字段回退（iterations vs iteration_count）

设计要点：
- 不依赖 Pydantic：用本地 Pydantic BaseModel（duck-typed on model_dump_json）
- 用 tmp_path 隔离 store
"""

# tests/unit/test_coding_store.py（agent: package-dashboard-api-v52）

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from kivi_agent.eval.coding_store import CodingResultStore

# ---- Mock 数据模型 ---------------------------------------------------------


class _MockCodingResult(BaseModel):
    """Mock CodingResult（H2 CodingEvalResult 的最小替代）。"""

    run_id: str
    task: str = ""
    started_at: str = "2026-01-01T00:00:00"
    finished_at: str | None = None
    completed: bool = False
    success: bool = False  # 别名（兼容 demo 数据）
    iterations: int = 0
    iteration_count: int = 0  # 别名
    patches: list[dict[str, Any]] = []
    test_runs: list[dict[str, Any]] = []


def _make_result(**kwargs: Any) -> _MockCodingResult:
    """构造 MockCodingResult（agent: package-dashboard-api-v52）。"""
    defaults: dict[str, Any] = {
        "run_id": "r-1",
        "task": "Write add(a,b)",
        "started_at": "2026-01-01T00:00:00",
        "finished_at": "2026-01-01T00:00:05",
        "completed": True,
    }
    defaults.update(kwargs)
    return _MockCodingResult(**defaults)


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    """临时 store 路径（agent: package-dashboard-api-v52）。"""
    return tmp_path / "coding.jsonl"


@pytest.fixture
def store(store_path: Path) -> CodingResultStore:
    """CodingResultStore 实例（agent: package-dashboard-api-v52）。"""
    return CodingResultStore(store_path)


# ---- 测试 ------------------------------------------------------------------


# 功能：save 追加写 + iter_all 读出一致
# 设计：3 条 coding result → iter_all 返回 3 条 dict
def test_save_and_iter(store: CodingResultStore) -> None:
    store.save(_make_result(run_id="r-1", task="add"))
    store.save(_make_result(run_id="r-2", task="fib"))
    store.save(_make_result(run_id="r-3", task="reverse"))

    rows = list(store.iter_all())
    assert len(rows) == 3
    assert rows[0]["task"] == "add"
    assert rows[1]["run_id"] == "r-2"
    assert rows[2]["task"] == "reverse"


# 功能：list_runs 按 started_at 倒序去重
# 设计：3 个 run 各 1 条，1 个 run 写 2 条（同 id 不同时间），验证去重 + 排序
def test_list_runs_dedup_and_sort(store: CodingResultStore) -> None:
    store.save(_make_result(run_id="r-1", started_at="2026-01-01T00:00:00"))
    store.save(_make_result(run_id="r-2", started_at="2026-01-03T00:00:00"))
    store.save(_make_result(run_id="r-3", started_at="2026-01-02T00:00:00"))
    # r-1 再写一次（新时间，应更新 latest 而非新增）
    store.save(_make_result(run_id="r-1", started_at="2026-01-04T00:00:00"))

    runs = store.list_runs()
    assert len(runs) == 3  # 去重
    # 按 started_at 倒序：r-1(新写) > r-2 > r-3
    run_ids = [r["run_id"] for r in runs]
    assert run_ids == ["r-1", "r-2", "r-3"]


# 功能：get_run 按 run_id 过滤
# 设计：跨多个 run 写入，get_run 只返回匹配行
def test_get_run_filters_by_id(store: CodingResultStore) -> None:
    store.save(_make_result(run_id="r-1", task="A"))
    store.save(_make_result(run_id="r-1", task="A2"))
    store.save(_make_result(run_id="r-2", task="B"))

    r1 = store.get_run("r-1")
    assert len(r1) == 2
    assert all(r["run_id"] == "r-1" for r in r1)

    r2 = store.get_run("r-2")
    assert len(r2) == 1
    assert r2[0]["task"] == "B"


# 功能：get_run 在 run_id 含 `..` 时抛 ValueError（路径遍历保护）
# 设计：恶意 run_id → 拒绝
def test_get_run_path_traversal(store: CodingResultStore) -> None:
    with pytest.raises(ValueError, match="invalid run_id"):
        store.get_run("..bad..")


# 功能：构造时拒绝含 `..` 的路径（路径遍历保护）
# 设计：构造 CodingResultStore(bad_path) → 抛 ValueError
def test_constructor_rejects_bad_path(tmp_path: Path) -> None:
    bad = tmp_path / ".." / "evil.jsonl"
    with pytest.raises(ValueError, match="invalid store path"):
        CodingResultStore(bad)


# 功能：save_batch 批量追加写 + 顺序保留
# 设计：批量 3 条 → iter_all 返回 3 条按写入顺序
def test_save_batch(store: CodingResultStore) -> None:
    batch = [
        _make_result(run_id="b-1"),
        _make_result(run_id="b-2"),
        _make_result(run_id="b-3"),
    ]
    store.save_batch(batch)

    rows = list(store.iter_all())
    assert len(rows) == 3
    assert [r["run_id"] for r in rows] == ["b-1", "b-2", "b-3"]


# 功能：list_runs 支持 limit/offset 分页
# 设计：3 个 run，limit=2 offset=1 → 返回 [r-2, r-1]
def test_list_runs_pagination(store: CodingResultStore) -> None:
    store.save(_make_result(run_id="r-1", started_at="2026-01-01T00:00:00"))
    store.save(_make_result(run_id="r-2", started_at="2026-01-02T00:00:00"))
    store.save(_make_result(run_id="r-3", started_at="2026-01-03T00:00:00"))

    page = store.list_runs(limit=2, offset=1)
    assert [r["run_id"] for r in page] == ["r-2", "r-1"]


# 功能：iterations 字段缺省时回退到 iteration_count
# 设计：iterations=0 + iteration_count=3 → list_runs 显示 3
def test_list_runs_iterations_fallback(store: CodingResultStore) -> None:
    store.save(
        _make_result(
            run_id="r-fb",
            iterations=0,
            iteration_count=5,
        )
    )
    runs = store.list_runs()
    assert runs[0]["iterations"] == 5


# 功能：completed 字段缺省时回退到 success
# 设计：用 _LegacyMock 只含 success 字段（无 completed）→ list_runs 显示 completed=True
def test_list_runs_completed_fallback(store: CodingResultStore) -> None:
    class _LegacyMock(BaseModel):
        run_id: str
        task: str = ""
        started_at: str = "2026-01-01T00:00:00"
        success: bool = False

    store.save(_LegacyMock(run_id="r-cf", success=True))
    runs = store.list_runs()
    assert runs[0]["completed"] is True
