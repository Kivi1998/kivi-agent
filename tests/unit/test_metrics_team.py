"""T11 6 团队指标单元测试（agent: package-eval-metrics-v52）。

# test_metrics_team.py（agent: package-eval-metrics-v52）
覆盖（plan §三 WT-H1）：
- 6 个指标 × 3 fixture ≈ 18+ case
- TeamMetricsReport.to_dict / to_json / 路径遍历保护
- compute_all_team_metrics 一键计算 6 指标
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from kivi_agent.eval.metrics import (
    AgentUtilizationMetric,
    CoordinationLatencyMetric,
    DelegationAccuracyMetric,
    HandoffQualityMetric,
    RoleConsistencyMetric,
    TeamSuccessRateMetric,
    compute_all_team_metrics,
)
from kivi_agent.eval.team.models import (
    DelegationStep,
    MemberOutcome,
    TeamEvalResult,
)

# ---------------------------------------------------------------------------
# Fixture 工厂
# ---------------------------------------------------------------------------

# 用哨兵区分"未传"和"显式 None"；显式 None 时透传（便于测跳过逻辑）
_UNSET: Any = object()


# 构造一个最小 TeamEvalResult 用于指标测试
def _team(
    team_id: str = "t1",
    success: bool = True,
    members: list[MemberOutcome] | None = None,
    delegations: list[DelegationStep] | None = None,
    total_messages: int = 0,
    successful_messages: int = 0,
    role_changes: int = 0,
    planned: dict[str, int] | None = None,
    actual: dict[str, int] | None = None,
    started_at: Any = _UNSET,
    finished_at: Any = _UNSET,
) -> TeamEvalResult:
    """构造最小 TeamEvalResult（agent: package-eval-metrics-v52）。

    设计：用 _UNSET 哨兵区分"未传"（用 base）和"显式 None"（透传 None）。
    显式 None 用于测试延迟指标跳过空时间戳。
    """
    base = "2026-07-23T10:00:00+00:00"
    t0 = base if started_at is _UNSET else started_at
    t1 = base if finished_at is _UNSET else finished_at
    return TeamEvalResult(
        team_id=team_id,
        goal=f"goal for {team_id}",
        started_at=t0,
        finished_at=t1,
        success=success,
        member_outcomes=members or [],
        delegation_chain=delegations or [],
        total_messages=total_messages,
        successful_messages=successful_messages,
        role_changes=role_changes,
        planned_assignments=planned or {},
        actual_assignments=actual or {},
    )


# 一个 2 成员（每个 1 sub_task）的基础 team
def _basic_team(success: bool = True) -> TeamEvalResult:
    """基础 2 成员 team：alice + bob 各 1 步、1 tool call、0 role change。"""
    return _team(
        team_id="t1",
        success=success,
        members=[
            MemberOutcome(name="alice", role="researcher", run_id="r1", success=True, tool_calls_count=1, steps=1),
            MemberOutcome(name="bob", role="writer", run_id="r2", success=True, tool_calls_count=1, steps=1),
        ],
        delegations=[
            DelegationStep(from_member="team", to_member="alice", sub_task="A"),
            DelegationStep(from_member="team", to_member="bob", sub_task="B"),
        ],
        total_messages=2,
        successful_messages=2,
        role_changes=0,
        planned={"alice": 1, "bob": 1},
        actual={"alice": 1, "bob": 1},
    )


# ---------------------------------------------------------------------------
# TeamSuccessRateMetric（3 fixture）
# ---------------------------------------------------------------------------


# 功能：全成功 team 时 rate=1.0 / passed=total
# 设计：2 个 success=True 的 team → rate=1.0
def test_team_success_rate_all_pass() -> None:
    results = [_basic_team(True), _basic_team(True)]
    out = TeamSuccessRateMetric().compute(results)
    assert out == {"rate": 1.0, "passed": 2, "total": 2}


# 功能：半数失败时 rate=0.5
# 设计：1 success + 1 fail → rate=0.5
def test_team_success_rate_half_pass() -> None:
    results = [_basic_team(True), _basic_team(False)]
    out = TeamSuccessRateMetric().compute(results)
    assert out == {"rate": 0.5, "passed": 1, "total": 2}


# 功能：空 results 短路返回，避免除零
# 设计：传空列表 → rate=0.0
def test_team_success_rate_empty_short_circuits() -> None:
    out = TeamSuccessRateMetric().compute([])
    assert out == {"rate": 0.0, "passed": 0, "total": 0}


# ---------------------------------------------------------------------------
# DelegationAccuracyMetric（3 fixture）
# ---------------------------------------------------------------------------


# 功能：planned == actual 时 rate=1.0
# 设计：3 team 全部 planned=actual → 全部命中
def test_delegation_accuracy_all_match() -> None:
    results = [
        _basic_team(True),
        _team(
            team_id="t2",
            planned={"alice": 2, "bob": 1},
            actual={"alice": 2, "bob": 1},
        ),
        _team(
            team_id="t3",
            planned={"alice": 1},
            actual={"alice": 1},
        ),
    ]
    out = DelegationAccuracyMetric().compute(results)
    assert out == {"rate": 1.0, "matched": 6, "planned_total": 6}


# 功能：部分委派错配时按 min(planned, actual) 累加
# 设计：1 team planned={alice: 1, bob: 1} actual={alice: 1} → 1/2
def test_delegation_accuracy_partial_match() -> None:
    results = [
        _team(
            team_id="t1",
            planned={"alice": 1, "bob": 1},
            actual={"alice": 1},  # bob 漏接
        )
    ]
    out = DelegationAccuracyMetric().compute(results)
    assert out == {"rate": 0.5, "matched": 1, "planned_total": 2}


# 功能：空 results 短路返回，避免除零
# 设计：传空列表 → rate=0.0 / matched=0
def test_delegation_accuracy_empty_short_circuits() -> None:
    out = DelegationAccuracyMetric().compute([])
    assert out == {"rate": 0.0, "matched": 0, "planned_total": 0}


# ---------------------------------------------------------------------------
# HandoffQualityMetric（3 fixture）
# ---------------------------------------------------------------------------


# 功能：所有消息都成功消费时 rate=1.0
# 设计：2 team 各 2 条消息全成功 → rate=1.0
def test_handoff_quality_all_successful() -> None:
    results = [
        _team(team_id="t1", total_messages=2, successful_messages=2),
        _team(team_id="t2", total_messages=3, successful_messages=3),
    ]
    out = HandoffQualityMetric().compute(results)
    assert out == {"rate": 1.0, "successful": 5, "total": 5}


# 功能：部分消息消费失败时按比例
# 设计：1 team 10 总 7 成功 → rate=0.7
def test_handoff_quality_partial() -> None:
    results = [_team(team_id="t1", total_messages=10, successful_messages=7)]
    out = HandoffQualityMetric().compute(results)
    assert out == {"rate": 0.7, "successful": 7, "total": 10}


# 功能：total=0 时短路返回 rate=0.0
# 设计：所有 team 都没有 mailbox 消息 → rate=0.0
def test_handoff_quality_no_messages_short_circuits() -> None:
    results = [
        _team(team_id="t1", total_messages=0, successful_messages=0),
        _team(team_id="t2", total_messages=0, successful_messages=0),
    ]
    out = HandoffQualityMetric().compute(results)
    assert out == {"rate": 0.0, "successful": 0, "total": 0}


# ---------------------------------------------------------------------------
# CoordinationLatencyMetric（3 fixture）
# ---------------------------------------------------------------------------


# 功能：单 team 1.5s 延迟
# 设计：t0=base, t1=base+1.5s → avg=1.5
def test_coordination_latency_single_team() -> None:
    t0 = "2026-07-23T10:00:00+00:00"
    t1 = "2026-07-23T10:00:01.500000+00:00"
    results = [_team(team_id="t1", started_at=t0, finished_at=t1)]
    out = CoordinationLatencyMetric().compute(results)
    assert out["avg_s"] == pytest.approx(1.5)
    assert out["count"] == 1


# 功能：4 team 延迟 1/2/3/4s，avg=2.5
# 设计：构造 4 个递增延迟的 team
def test_coordination_latency_multi_team_percentiles() -> None:
    base = datetime.fromisoformat("2026-07-23T10:00:00+00:00")
    results = []
    for i, secs in enumerate([1.0, 2.0, 3.0, 4.0]):
        t0 = base.isoformat()
        t1 = (base + timedelta(seconds=secs)).isoformat()
        results.append(_team(team_id=f"t{i}", started_at=t0, finished_at=t1))
    out = CoordinationLatencyMetric().compute(results)
    assert out["avg_s"] == pytest.approx(2.5)
    assert out["count"] == 4
    assert out["p50_s"] == pytest.approx(3.0)
    assert out["p95_s"] == pytest.approx(4.0)


# 功能：缺时间戳或非法格式的 team 被跳过
# 设计：3 team 中 1 个缺 finished_at + 1 个 ISO 错
def test_coordination_latency_skips_invalid() -> None:
    base = "2026-07-23T10:00:00+00:00"
    results = [
        _team(team_id="t1", started_at=base, finished_at=base),  # 0s 计入
        _team(team_id="t2", started_at=base, finished_at=None),  # 跳过
        _team(team_id="t3", started_at="not-iso", finished_at="also-not-iso"),  # 跳过
    ]
    out = CoordinationLatencyMetric().compute(results)
    assert out["count"] == 1
    assert out["avg_s"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# AgentUtilizationMetric（3 fixture）
# ---------------------------------------------------------------------------


# 功能：每个 step-member cell 都有 tool call 时 rate=1.0
# 设计：1 成员 × 1 step × 1 tool → total_tool=1, step_x_member=1 → rate=1.0
def test_agent_utilization_full() -> None:
    results = [
        _team(
            team_id="t1",
            members=[
                MemberOutcome(name="a", role="r", run_id="r1", tool_calls_count=1, steps=1),
            ],
        )
    ]
    out = AgentUtilizationMetric().compute(results)
    assert out["rate"] == pytest.approx(1.0)
    assert out["tool_calls"] == 1
    assert out["step_x_member"] == 1


# 功能：半数 step-member cell 有 tool call 时 rate=0.5
# 设计：1 成员 × 2 step × 1 tool = total_tool=1, step_x_member=2 → rate=0.5
def test_agent_utilization_half() -> None:
    results = [
        _team(
            team_id="t1",
            members=[
                MemberOutcome(name="a", role="r", run_id="r1", tool_calls_count=1, steps=2),
            ],
        )
    ]
    out = AgentUtilizationMetric().compute(results)
    assert out["rate"] == pytest.approx(0.5)
    assert out["raw_rate"] == pytest.approx(0.5)


# 功能：空 members 短路返回 rate=0.0
# 设计：team members=[] → 不计入；多 team 都没 member → rate=0
def test_agent_utilization_no_members_short_circuits() -> None:
    results = [
        _team(team_id="t1", members=[]),
        _team(team_id="t2", members=[]),
    ]
    out = AgentUtilizationMetric().compute(results)
    assert out["rate"] == 0.0
    assert out["tool_calls"] == 0
    assert out["step_x_member"] == 0


# ---------------------------------------------------------------------------
# RoleConsistencyMetric（3 fixture）
# ---------------------------------------------------------------------------


# 功能：全部无 role 变化时 rate=1.0
# 设计：1 team role_changes=0, total_steps=2 → rate=1.0
def test_role_consistency_no_change() -> None:
    results = [
        _team(
            team_id="t1",
            members=[
                MemberOutcome(name="a", role="r", run_id="r1", steps=1),
                MemberOutcome(name="b", role="w", run_id="r2", steps=1),
            ],
            role_changes=0,
        )
    ]
    out = RoleConsistencyMetric().compute(results)
    assert out == {"rate": 1.0, "role_changes": 0, "total_steps": 2}


# 功能：1 次 role 变化 + 4 总步数 → rate=0.75
# 设计：role_changes=1, total_steps=4 → 1 - 1/4 = 0.75
def test_role_consistency_one_change_in_four_steps() -> None:
    results = [
        _team(
            team_id="t1",
            members=[
                MemberOutcome(name="a", role="r", run_id="r1", steps=4),
            ],
            role_changes=1,
        )
    ]
    out = RoleConsistencyMetric().compute(results)
    assert out["rate"] == pytest.approx(0.75)
    assert out["role_changes"] == 1
    assert out["total_steps"] == 4


# 功能：所有 steps=0 时 rate=1.0（避免除零）
# 设计：空 members + role_changes=0 → rate=1.0
def test_role_consistency_zero_steps_returns_one() -> None:
    results = [_team(team_id="t1", members=[], role_changes=0)]
    out = RoleConsistencyMetric().compute(results)
    assert out == {"rate": 1.0, "role_changes": 0, "total_steps": 0}


# ---------------------------------------------------------------------------
# TeamMetricsReport + compute_all_team_metrics
# ---------------------------------------------------------------------------


# 功能：compute_all_team_metrics 一键输出 6 指标 + dataset 元信息
# 设计：1 个全成功 case → 断言 6 个 name 键 + dataset_name + team_count
def test_compute_all_team_metrics_returns_six() -> None:
    results = [_basic_team(True)]
    report = compute_all_team_metrics(results, dataset_name="demo")

    assert report.dataset_name == "demo"
    assert report.team_count == 1
    assert set(report.metrics.keys()) == {
        "team_success_rate",
        "delegation_accuracy",
        "handoff_quality",
        "coordination_latency_seconds",
        "agent_utilization",
        "role_consistency",
    }


# 功能：TeamMetricsReport.to_dict 输出 dataclass 全字段
# 设计：构造 report → to_dict → 断言字段一一对应
def test_team_metrics_report_to_dict() -> None:
    results = [_basic_team(True)]
    report = compute_all_team_metrics(results, dataset_name="t")
    d = report.to_dict()

    assert d["dataset_name"] == "t"
    assert d["team_count"] == 1
    assert "metrics" in d
    assert "team_success_rate" in d["metrics"]
    assert "generated_at" in d
    assert d["generated_at"]


# 功能：TeamMetricsReport.to_json 写入合法 UTF-8 JSON
# 设计：写入 tmp_path → 读回 JSON 验证
def test_team_metrics_report_to_json_roundtrip(tmp_path: Path) -> None:
    results = [_basic_team(True)]
    report = compute_all_team_metrics(results, dataset_name="t")
    out_path = tmp_path / "report.json"
    report.to_json(out_path)

    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["dataset_name"] == "t"
    assert data["metrics"]["team_success_rate"]["rate"] == 1.0


# 功能：路径含 ".." 时 to_json 直接拒绝
# 设计：构造含 ".." 段的 Path → 断言抛 ValueError
def test_team_metrics_report_to_json_rejects_traversal() -> None:
    results = [_basic_team(True)]
    report = compute_all_team_metrics(results, dataset_name="t")
    bad = Path("safe") / ".." / "evil.json"

    with pytest.raises(ValueError, match="invalid path"):
        report.to_json(bad)


# 功能：多 team 混合时各指标正确聚合
# 设计：2 team（一成一败）→ 验证每个指标的具体数值
def test_compute_all_team_metrics_mixed_batch() -> None:
    base = "2026-07-23T10:00:00+00:00"
    t1 = "2026-07-23T10:00:01+00:00"  # 1s 延迟
    t2 = "2026-07-23T10:00:03+00:00"  # 3s 延迟
    results = [
        _team(
            team_id="ok",
            success=True,
            started_at=base,
            finished_at=t1,
            members=[
                MemberOutcome(name="a", role="r", run_id="r1", success=True, tool_calls_count=1, steps=1),
                MemberOutcome(name="b", role="w", run_id="r2", success=True, tool_calls_count=1, steps=1),
            ],
            total_messages=2,
            successful_messages=2,
            planned={"a": 1, "b": 1},
            actual={"a": 1, "b": 1},
        ),
        _team(
            team_id="bad",
            success=False,
            started_at=base,
            finished_at=t2,
            members=[
                MemberOutcome(name="a", role="r", run_id="r3", success=True, tool_calls_count=2, steps=2),
            ],
            total_messages=1,
            successful_messages=0,
            planned={"a": 1, "b": 1},
            actual={"a": 1},
        ),
    ]
    report = compute_all_team_metrics(results, dataset_name="mixed")
    m = report.metrics

    # team_success_rate: 1/2
    assert m["team_success_rate"]["rate"] == 0.5
    # delegation_accuracy: ok 命中 2, bad 命中 1（b 漏）→ 3/4 = 0.75
    assert m["delegation_accuracy"]["rate"] == pytest.approx(0.75)
    # handoff_quality: 2/3 ≈ 0.667
    assert m["handoff_quality"]["rate"] == pytest.approx(2 / 3, rel=1e-3)
    # agent_utilization: ok (2 tool / 2 steps×2 members = 0.5) +
    #   bad (2 tool / 2 steps×1 member = 1.0) → total_tool=4, total_step_x_member=6
    assert m["agent_utilization"]["raw_rate"] == pytest.approx(4 / 6, rel=1e-3)


# 功能：所有指标的 description 字段非空（前端 tooltip 用）
# 设计：compute_all_team_metrics 后逐指标断言 description
def test_all_team_metrics_have_description() -> None:
    results = [_basic_team(True)]
    report = compute_all_team_metrics(results, dataset_name="t")

    for name, body in report.metrics.items():
        assert "description" in body, f"{name} missing description"
        assert body["description"], f"{name} description is empty"
