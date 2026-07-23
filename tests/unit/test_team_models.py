"""TeamCase / TeamEvalResult / MailboxTracker 单元测试（agent: package-eval-team-v52）。

# test_team_models.py（agent: package-eval-team-v52）
覆盖 6 个核心场景：
1. TeamCase 字段填充 + 默认值
2. TeamDataset.load 解析有效 JSONL
3. TeamDataset.load 含 ".." 路径段 → 拒绝
4. TeamDataset.load 含非法 JSON → ValueError + 行号
5. filter_by_difficulty 按难度过滤
6. MailboxTracker write/consume 状态同步
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from kivi_agent.eval.team.mailbox_tracker import MailboxTracker
from kivi_agent.eval.team.models import (
    DelegationStep,
    MemberOutcome,
    MemberSpec,
    SubTaskSpec,
    TeamCase,
    TeamDataset,
    TeamEvalResult,
)


# 写 JSONL 文件（fixture helper）
def _write_team_cases(path: Path, cases: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


# 功能：TeamCase 字段全部填充 + 默认值正确
# 设计：构造 1 个完整 TeamCase（成员 + 子任务 + 期望分配），
#       断言 member_specs/sub_tasks/expected_assignments 等字段
def test_team_case_fields_populated_correctly() -> None:
    case = TeamCase(
        id="team-1",
        goal="research and write a report",
        member_specs=[
            MemberSpec(name="alice", role="researcher", prompt="search X"),
            MemberSpec(name="bob", role="writer", prompt="write summary"),
        ],
        sub_tasks=[
            SubTaskSpec(assignee="alice", topic="X"),
            SubTaskSpec(assignee="bob", topic="summarize"),
        ],
        expected_assignments={"alice": 1, "bob": 1},
        expected_total_messages=2,
        max_steps_per_member=8,
        difficulty="medium",
    )

    assert case.id == "team-1"
    assert case.goal == "research and write a report"
    assert len(case.member_specs) == 2
    assert case.member_specs[0].role == "researcher"
    assert case.member_specs[1].name == "bob"
    assert case.sub_tasks[0].assignee == "alice"
    assert case.expected_assignments == {"alice": 1, "bob": 1}
    assert case.expected_total_messages == 2
    assert case.max_steps_per_member == 8
    assert case.difficulty == "medium"
    assert case.notes is None


# 功能：TeamCase 默认值（无 member_specs/sub_tasks）正确
# 设计：只填 id + goal；断言 default factory 给空 list + 默认 difficulty
def test_team_case_default_values() -> None:
    case = TeamCase(id="t", goal="g")
    assert case.member_specs == []
    assert case.sub_tasks == []
    assert case.expected_assignments == {}
    assert case.expected_total_messages == 0
    assert case.max_steps_per_member == 10
    assert case.difficulty == "medium"


# 功能：TeamDataset.load 解析有效 JSONL 后字段全部填充
# 设计：写 2 个 case → 解析后断言 cases 数 + 各 case 字段
def test_team_dataset_load_valid_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "team.jsonl"
    _write_team_cases(p, [
        {
            "id": "t1",
            "goal": "research X",
            "member_specs": [{"name": "alice", "role": "researcher"}],
            "sub_tasks": [{"assignee": "alice", "topic": "X"}],
            "expected_assignments": {"alice": 1},
            "difficulty": "easy",
        },
        {
            "id": "t2",
            "goal": "summarize",
            "member_specs": [{"name": "bob", "role": "writer"}],
            "sub_tasks": [],
            "difficulty": "hard",
        },
    ])

    ds = TeamDataset.load(p)

    assert ds.name == "team"
    assert len(ds.cases) == 2
    assert ds.cases[0].id == "t1"
    assert ds.cases[0].difficulty == "easy"
    assert ds.cases[0].member_specs[0].name == "alice"
    assert ds.cases[1].sub_tasks == []


# 功能：TeamDataset.load 含 ".." 路径段时直接拒绝
# 设计：构造 Path("foo/../bad.jsonl")；断言抛 ValueError + 错误消息含路径
def test_team_dataset_load_rejects_path_traversal() -> None:
    bad_path = Path("some/../malicious.jsonl")
    assert ".." in bad_path.parts

    with pytest.raises(ValueError) as exc:
        TeamDataset.load(bad_path)
    assert "invalid team dataset path" in str(exc.value)


# 功能：TeamDataset.load 含非法 JSON 时抛 ValueError + 行号
# 设计：第 2 行放非法 JSON；断言错误消息含 "line 2"
def test_team_dataset_load_invalid_json_raises_with_line_number(tmp_path: Path) -> None:
    p = tmp_path / "bad.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        f.write(json.dumps({"id": "ok", "goal": "x"}) + "\n")
        f.write("{not valid json}\n")

    with pytest.raises(ValueError) as exc:
        TeamDataset.load(p)
    assert "line 2" in str(exc.value)


# 功能：filter_by_difficulty 按难度过滤并返回新 dataset（name 带后缀）
# 设计：3 个 case 不同 difficulty → filter("easy") 留下 1 个
def test_team_dataset_filter_by_difficulty(tmp_path: Path) -> None:
    p = tmp_path / "ds.jsonl"
    _write_team_cases(p, [
        {"id": "a", "goal": "g1", "difficulty": "easy"},
        {"id": "b", "goal": "g2", "difficulty": "hard"},
        {"id": "c", "goal": "g3", "difficulty": "easy"},
    ])
    ds = TeamDataset.load(p)

    filtered = ds.filter_by_difficulty("easy")

    assert filtered.name == "ds_diff_easy"
    assert [c.id for c in filtered.cases] == ["a", "c"]


# 功能：MailboxTracker record_write 推 DelegationStep，record_consume 累加计数
# 设计：2 次 write + 1 次 consume → 委派链含 2 步 + successful=1 + total=1
def test_mailbox_tracker_write_and_consume_aggregate() -> None:
    tracker = MailboxTracker()
    step1 = tracker.record_write("alice", "team", "do X", sub_task="X")
    step2 = tracker.record_write("bob", "alice", "review please", sub_task="review")
    consumed = tracker.record_consume(
        "bob", [{"sender": "alice", "content": "review", "ts": "2026-07-23T10:00:00"}]
    )

    assert len(tracker.delegation_chain) == 2
    assert isinstance(step1, DelegationStep)
    assert step1.from_member == "team" and step1.to_member == "alice"
    assert step2.from_member == "alice" and step2.to_member == "bob"
    assert tracker.total_messages == 1
    assert tracker.successful_messages == 1
    assert consumed == 1
    assert tracker.messages_by_recipient() == {"alice": 1, "bob": 1}


# 功能：MailboxTracker.attach_to 把状态同步到 TeamEvalResult（含 handoff 事件）
# 设计：2 次 write + 1 次 consume → attach_to → result 含 2 委派步骤 +
#       total/successful 计数 + 2 个 team.handoff 事件
def test_mailbox_tracker_attach_to_team_eval_result() -> None:
    tracker = MailboxTracker()
    tracker.record_write("alice", "team", "do X", sub_task="X")
    tracker.record_write("bob", "alice", "review", sub_task="review")
    tracker.record_consume("bob", [{"sender": "alice", "content": "review"}])

    result = TeamEvalResult(team_id="t1", goal="g")
    tracker.attach_to(result, emit_events=True)

    assert len(result.delegation_chain) == 2
    assert result.total_messages == 1
    assert result.successful_messages == 1
    handoff_events = [e for e in result.events if e.type == "team.handoff"]
    assert len(handoff_events) == 2


# 功能：MemberOutcome 默认值正确
# 设计：只填 name + run_id；断言 success=False, tool_calls=0, steps=0, finished_at=None
def test_member_outcome_default_values() -> None:
    outcome = MemberOutcome(name="alice", role="r", run_id="run-1")
    assert outcome.success is False
    assert outcome.tool_calls_count == 0
    assert outcome.steps == 0
    assert outcome.finished_at is None


# 功能：TeamEvalResult 默认值正确
# 设计：只填 team_id + goal；断言 started_at 自动生成 + 其余字段默认空
def test_team_eval_result_default_values() -> None:
    result = TeamEvalResult(team_id="t1", goal="g")
    assert result.team_id == "t1"
    assert result.goal == "g"
    assert result.started_at  # 自动生成非空
    assert result.finished_at is None
    assert result.success is False
    assert result.error is None
    assert result.member_outcomes == []
    assert result.delegation_chain == []
    assert result.events == []
    assert result.total_messages == 0
    assert result.successful_messages == 0
    assert result.role_changes == 0
    assert result.planned_assignments == {}
    assert result.actual_assignments == {}


# 功能：TeamDataset.load + JSONL 解析（spec 字段全部覆盖）
# 设计：构造一个 case 含所有 JSONL 字段 → 解析后逐字段断言
def test_team_dataset_load_full_spec_fields(tmp_path: Path) -> None:
    p = tmp_path / "team.jsonl"
    _write_team_cases(p, [
        {
            "id": "t1",
            "goal": "research",
            "member_specs": [{"name": "a", "role": "researcher", "prompt": "p"}],
            "sub_tasks": [{"assignee": "a", "topic": "x"}],
            "expected_assignments": {"a": 1},
            "expected_total_messages": 1,
            "max_steps_per_member": 5,
            "difficulty": "hard",
            "notes": "demo case",
        }
    ])

    ds = TeamDataset.load(p)
    c = ds.cases[0]
    assert c.member_specs[0].prompt == "p"
    assert c.expected_total_messages == 1
    assert c.max_steps_per_member == 5
    assert c.difficulty == "hard"
    assert c.notes == "demo case"
