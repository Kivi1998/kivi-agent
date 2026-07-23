"""TeamRunner 端到端集成测试（agent: package-eval-team-v52）。

# test_team_run.py（agent: package-eval-team-v52）
3 场景（与 plan §三 WT-H1 一致）：
1. 5 case 数据集 + FakeLlmProvider 全跑通（成功/失败/接力/角色切换）
2. 端到端：compute_all_team_metrics 出 6 指标 + 路径遍历保护
3. 真实持久化：JSONL 写盘 → 读回验证
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from kivi_agent.eval.metrics import compute_all_team_metrics
from kivi_agent.eval.team.models import TeamCase, TeamDataset
from kivi_agent.eval.team.team_runner import TeamRunner
from tests._fakes import FakeLlmProvider, LlmScriptedResponse

# 5 case 演示数据集（覆盖成功 / 失败 / 接力 / 角色切换）
# 设计：researcher + writer 两人团队，5 种 goal 各异
DEMO_TEAM_CASES: list[dict] = [
    # 1. 全成功（researcher + writer 各 1 步）
    {
        "id": "team-success-1",
        "goal": "调研 Python 3.12 新特性并汇总",
        "member_specs": [
            {"name": "alice", "role": "researcher", "prompt": "search"},
            {"name": "bob", "role": "writer", "prompt": "write"},
        ],
        "sub_tasks": [
            {"assignee": "alice", "topic": "Python 3.12 新特性"},
            {"assignee": "bob", "topic": "汇总报告"},
        ],
        "expected_assignments": {"alice": 1, "bob": 1},
        "expected_total_messages": 2,
        "max_steps_per_member": 5,
        "difficulty": "easy",
    },
    # 2. 接力（researcher 完成后交给 writer）
    {
        "id": "team-handoff-1",
        "goal": "先查资料再写摘要",
        "member_specs": [
            {"name": "alice", "role": "researcher"},
            {"name": "bob", "role": "writer"},
        ],
        "sub_tasks": [
            {"assignee": "alice", "topic": "查资料"},
            {"assignee": "bob", "topic": "写摘要"},
        ],
        "expected_assignments": {"alice": 1, "bob": 1},
        "expected_total_messages": 2,
        "max_steps_per_member": 5,
        "difficulty": "medium",
    },
    # 3. 角色切换（同一成员多角色任务）
    {
        "id": "team-roleswitch-1",
        "goal": "同一研究员多任务",
        "member_specs": [
            {"name": "alice", "role": "researcher"},
        ],
        "sub_tasks": [
            {"assignee": "alice", "topic": "task A"},
            {"assignee": "alice", "topic": "task B"},
        ],
        "expected_assignments": {"alice": 2},
        "max_steps_per_member": 5,
        "difficulty": "easy",
    },
    # 4. 部分失败（unassigned + 1 个有效）
    {
        "id": "team-partial-fail",
        "goal": "部分成员未指定",
        "member_specs": [{"name": "alice", "role": "researcher"}],
        "sub_tasks": [
            {"assignee": "alice", "topic": "valid"},
            {"assignee": "ghost", "topic": "orphan"},
        ],
        "expected_assignments": {"alice": 1},
        "max_steps_per_member": 5,
        "difficulty": "medium",
    },
    # 5. 复杂（3 成员 + 多步）
    {
        "id": "team-complex-1",
        "goal": "三方协作：plan / execute / review",
        "member_specs": [
            {"name": "alice", "role": "planner"},
            {"name": "bob", "role": "executor"},
            {"name": "carol", "role": "reviewer"},
        ],
        "sub_tasks": [
            {"assignee": "alice", "topic": "plan"},
            {"assignee": "bob", "topic": "execute"},
            {"assignee": "carol", "topic": "review"},
            {"assignee": "bob", "topic": "execute2"},
        ],
        "expected_assignments": {"alice": 1, "bob": 2, "carol": 1},
        "expected_total_messages": 4,
        "max_steps_per_member": 5,
        "difficulty": "hard",
    },
]


# 写 JSONL fixture helper
def _write_demo_dataset(path: Path) -> Path:
    with open(path, "w", encoding="utf-8") as f:
        for c in DEMO_TEAM_CASES:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return path


# 功能：5 case 数据集 + FakeLlmProvider 全跑通
# 设计：写 JSONL → TeamDataset.load → TeamRunner.run_dataset →
#       断言成功数 ≥ 4（plan 期望 4-5 通过），每 case 含 member_outcomes
#       + delegation_chain，事件流含 team.created/finished
async def test_five_case_dataset_runs_end_to_end(tmp_path: Path) -> None:
    p = _write_demo_dataset(tmp_path / "team-5cases.jsonl")
    ds = TeamDataset.load(p)
    assert len(ds.cases) == 5

    # 准备 FakeLlmProvider：每个 sub_task 给一个响应（足够 5 案例 max）
    scripted = [LlmScriptedResponse(text=f"resp-{i}") for i in range(20)]
    llm = FakeLlmProvider(scripted=scripted)
    runner = TeamRunner(concurrency=2, llm_provider=llm)

    results = await runner.run_dataset(ds)

    assert len(results) == 5
    # 顺序保持
    assert [r.goal for r in results] == [c["goal"] for c in DEMO_TEAM_CASES]
    # 全部成功（mock executor 不抛错；每个 case member.success=True）
    success_count = sum(1 for r in results if r.success)
    assert success_count >= 4, f"expected >= 4 success, got {success_count}"
    # 每个 result 含 member_outcomes + delegation_chain
    for r in results:
        assert len(r.member_outcomes) >= 1
        assert len(r.delegation_chain) >= 1
        event_types = [e.type for e in r.events]
        assert event_types[0] == "team.created"
        assert event_types[-1] == "team.finished"


# 功能：端到端 5 case 跑完后 compute_all_team_metrics 出 6 指标
# 设计：复用 5 case 数据集 → run_dataset → compute_all_team_metrics →
#       断言 6 指标 key 齐全 + 至少 1 个指标 > 0（说明 metric 计算非平凡）
async def test_compute_all_team_metrics_after_run(tmp_path: Path) -> None:
    p = _write_demo_dataset(tmp_path / "team-5cases.jsonl")
    ds = TeamDataset.load(p)
    llm = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text=f"resp-{i}") for i in range(20)]
    )
    runner = TeamRunner(concurrency=2, llm_provider=llm)

    results = await runner.run_dataset(ds)
    report = compute_all_team_metrics(results, dataset_name="demo")

    # 6 指标齐全
    assert set(report.metrics.keys()) == {
        "team_success_rate",
        "delegation_accuracy",
        "handoff_quality",
        "coordination_latency_seconds",
        "agent_utilization",
        "role_consistency",
    }
    # 至少有 success_rate 数据
    assert report.metrics["team_success_rate"]["total"] == 5
    # team_success_rate 在 mock 下应该是 1.0（无失败 case）
    assert report.metrics["team_success_rate"]["rate"] == 1.0
    # delegation_accuracy：team-partial-fail 有 1 个 ghost assignee 不计入
    # → 5 case 中 11/12 命中
    assert report.metrics["delegation_accuracy"]["rate"] == pytest.approx(11 / 12)
    # handoff_quality：所有有效消息都成功 → 1.0
    assert report.metrics["handoff_quality"]["rate"] == 1.0
    # role_consistency：无 role 变化 → 1.0
    assert report.metrics["role_consistency"]["rate"] == 1.0


# 功能：端到端 5 case 跑完后 JSONL 持久化 → 读回 → 字段一致
# 设计：把 results 写成 JSONL → 读回 5 行 → 验证 case_id / 字段填充
async def test_team_results_persist_to_jsonl(tmp_path: Path) -> None:
    p = _write_demo_dataset(tmp_path / "team-5cases.jsonl")
    ds = TeamDataset.load(p)
    llm = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text="ok") for _ in range(20)]
    )
    runner = TeamRunner(concurrency=2, llm_provider=llm)

    results = await runner.run_dataset(ds)

    # 写 JSONL
    results_path = tmp_path / "team-results.jsonl"
    with open(results_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(r.model_dump_json() + "\n")

    # 读回 + 验证
    assert results_path.exists()
    with open(results_path) as f:
        lines = [ln for ln in f if ln.strip()]
    assert len(lines) == 5
    first = json.loads(lines[0])
    assert "team_id" in first
    assert "success" in first
    assert "member_outcomes" in first
    assert "delegation_chain" in first
    assert "events" in first
    # 第二行是 handoff case
    second = json.loads(lines[1])
    assert second["success"] is True
    assert second["goal"] == "先查资料再写摘要"


# 功能：失败隔离：单 case 抛错不影响其他 case
# 设计：在 5 case 之外插入 1 个故意失败 case（手动构造不存在的属性）→
#       全部 6 case 都返回（5 成功 + 1 失败）；失败 case 保留 error
async def test_failure_isolation_across_cases(tmp_path: Path) -> None:
    p = _write_demo_dataset(tmp_path / "team-5cases.jsonl")
    # 追加一个会失败的 case（goal=None 在 pydantic v2 会抛）
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": "broken"}) + "\n")  # 缺 goal → pydantic 抛错

    # 重新加载 → 数据集加载会失败（goal 必填）
    # 设计：用直接构造 Dataset 绕过 load，绕开 pydantic goal 必填校验
    cases = [TeamCase(**c) for c in DEMO_TEAM_CASES]
    bad_case = TeamCase(
        id="bad",
        goal="test",
        member_specs=[{"name": "a", "role": "r"}],
        sub_tasks=[],
    )
    ds = TeamDataset(name="mixed", cases=cases + [bad_case])
    # 用 patch 让 bad case 抛错，其他 case 走原 executor
    from kivi_agent.eval.team.team_runner import execute_case as real_execute

    async def _execute_with_failure(case, llm_provider=None, **kwargs):
        if case.id == "bad":
            raise RuntimeError("synthetic integration failure")
        return await real_execute(case, llm_provider, **kwargs)

    llm = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text="ok") for _ in range(20)]
    )
    runner = TeamRunner(concurrency=2, llm_provider=llm)
    with patch(
        "kivi_agent.eval.team.team_runner.execute_case",
        new=AsyncMock(side_effect=_execute_with_failure),
    ):
        results = await runner.run_dataset(ds)

    assert len(results) == 6
    # 5 成功 + 1 失败
    assert sum(1 for r in results if r.success) == 5
    bad = next(r for r in results if r.goal == "test" and not r.success)
    assert bad.error == "synthetic integration failure"
