"""TeamResultStore 单元测试（WT-H3 / agent: package-dashboard-api-v52）。

测试目标：
1. JSONL 追加写 + iter_all 读取一致
2. list_teams 按 started_at 倒序去重
3. get_team 按 team_id 过滤
4. 路径遍历保护：拒绝 `..` 段 / `..` in team_id
5. save_batch 批量写入

设计要点：
- 不依赖 Pydantic：用本地 Pydantic BaseModel（duck-typed on model_dump_json）
- 用 tmp_path 隔离 store
"""

# tests/unit/test_team_store.py（agent: package-dashboard-api-v52）

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from kivi_agent.eval.team_store import TeamResultStore


# ---- Mock 数据模型 ---------------------------------------------------------


class _MockTeamResult(BaseModel):
    """Mock TeamResult（H1 TeamEvalResult 的最小替代）。"""

    team_id: str
    goal: str = ""
    started_at: str = "2026-01-01T00:00:00"
    finished_at: str | None = None
    success: bool = False
    member_specs: list[dict[str, Any]] = []
    member_count: int = 0
    member_outcomes: list[dict[str, Any]] = []
    delegations: list[dict[str, Any]] = []


def _make_result(**kwargs: Any) -> _MockTeamResult:
    """构造 MockTeamResult（agent: package-dashboard-api-v52）。"""
    defaults: dict[str, Any] = {
        "team_id": "t-1",
        "goal": "compare X and Y",
        "started_at": "2026-01-01T00:00:00",
        "finished_at": "2026-01-01T00:00:05",
        "success": True,
    }
    defaults.update(kwargs)
    return _MockTeamResult(**defaults)


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    """临时 store 路径（agent: package-dashboard-api-v52）。"""
    return tmp_path / "teams.jsonl"


@pytest.fixture
def store(store_path: Path) -> TeamResultStore:
    """TeamResultStore 实例（agent: package-dashboard-api-v52）。"""
    return TeamResultStore(store_path)


# ---- 测试 ------------------------------------------------------------------


# 功能：save 追加写 + iter_all 读出一致
# 设计：3 条 team result → iter_all 返回 3 条 dict
def test_save_and_iter(store: TeamResultStore) -> None:
    store.save(_make_result(team_id="t-1", goal="A"))
    store.save(_make_result(team_id="t-2", goal="B"))
    store.save(_make_result(team_id="t-3", goal="C"))

    rows = list(store.iter_all())
    assert len(rows) == 3
    assert rows[0]["team_id"] == "t-1"
    assert rows[1]["goal"] == "B"
    assert rows[2]["team_id"] == "t-3"


# 功能：list_teams 按 started_at 倒序去重
# 设计：3 个 team 各 1 条，1 个 team 写 2 条（同 id 不同时间），验证去重 + 排序
def test_list_teams_dedup_and_sort(store: TeamResultStore) -> None:
    # t-1: 旧
    store.save(_make_result(team_id="t-1", started_at="2026-01-01T00:00:00"))
    # t-2: 新
    store.save(_make_result(team_id="t-2", started_at="2026-01-03T00:00:00"))
    # t-3: 中
    store.save(_make_result(team_id="t-3", started_at="2026-01-02T00:00:00"))
    # t-1 再写一次（新时间，应更新 latest 而非新增）
    store.save(_make_result(team_id="t-1", started_at="2026-01-04T00:00:00"))

    teams = store.list_teams()
    assert len(teams) == 3  # 去重
    # 按 started_at 倒序：t-1(新写) > t-2 > t-3
    team_ids = [t["team_id"] for t in teams]
    assert team_ids == ["t-1", "t-2", "t-3"]


# 功能：get_team 按 team_id 过滤
# 设计：跨多个 team 写入，get_team 只返回匹配行
def test_get_team_filters_by_id(store: TeamResultStore) -> None:
    store.save(_make_result(team_id="t-1", goal="A"))
    store.save(_make_result(team_id="t-1", goal="A2"))
    store.save(_make_result(team_id="t-2", goal="B"))

    t1 = store.get_team("t-1")
    assert len(t1) == 2
    assert all(r["team_id"] == "t-1" for r in t1)

    t2 = store.get_team("t-2")
    assert len(t2) == 1
    assert t2[0]["goal"] == "B"


# 功能：get_team 在 team_id 含 `..` 时抛 ValueError（路径遍历保护）
# 设计：恶意 team_id → 拒绝
def test_get_team_path_traversal(store: TeamResultStore) -> None:
    with pytest.raises(ValueError, match="invalid team_id"):
        store.get_team("..bad..")


# 功能：构造时拒绝含 `..` 的路径（路径遍历保护）
# 设计：构造 EvalResultStore(bad_path) → 抛 ValueError
def test_constructor_rejects_bad_path(tmp_path: Path) -> None:
    bad = tmp_path / ".." / "evil.jsonl"
    with pytest.raises(ValueError, match="invalid store path"):
        TeamResultStore(bad)


# 功能：save_batch 批量追加写 + 顺序保留
# 设计：批量 3 条 → iter_all 返回 3 条按写入顺序
def test_save_batch(store: TeamResultStore) -> None:
    batch = [
        _make_result(team_id="b-1"),
        _make_result(team_id="b-2"),
        _make_result(team_id="b-3"),
    ]
    store.save_batch(batch)

    rows = list(store.iter_all())
    assert len(rows) == 3
    assert [r["team_id"] for r in rows] == ["b-1", "b-2", "b-3"]


# 功能：list_teams 支持 limit/offset 分页
# 设计：3 个 team，limit=2 offset=1 → 返回 [t-2, t-3]
def test_list_teams_pagination(store: TeamResultStore) -> None:
    store.save(_make_result(team_id="t-1", started_at="2026-01-01T00:00:00"))
    store.save(_make_result(team_id="t-2", started_at="2026-01-02T00:00:00"))
    store.save(_make_result(team_id="t-3", started_at="2026-01-03T00:00:00"))

    page = store.list_teams(limit=2, offset=1)
    assert [t["team_id"] for t in page] == ["t-2", "t-1"]


# 功能：list_teams 在 member_specs 缺 member_count 时回退用 spec 数量
# 设计：member_count=0 + member_specs=[3 个] → summary 用 3
def test_list_teams_member_count_fallback(store: TeamResultStore) -> None:
    store.save(
        _make_result(
            team_id="t-fb",
            member_count=0,
            member_specs=[{"name": "a"}, {"name": "b"}, {"name": "c"}],
        )
    )
    teams = store.list_teams()
    assert teams[0]["member_count"] == 3
