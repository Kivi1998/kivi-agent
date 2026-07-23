"""TeamRunner / team_executor 单元测试（agent: package-eval-team-v52）。

# test_team_runner.py（agent: package-eval-team-v52）
覆盖 8+ 核心场景：
1. run_case 单 case 委派 → TeamEvalResult.success=True + member_outcomes 完整
2. run_dataset 并发跑：结果数 == cases 数 + 顺序保持
3. 失败隔离：单 case 抛异常 → 转 success=False + error 字段；不阻塞其他
4. 委派链：每个 sub_task 一条 DelegationStep（from=team / to=assignee）
5. mailbox tracker 集成：successful/total_messages 计数正确
6. 成员未指定：sub_task 委派到不存在的 member → 记 team.unassigned 事件
7. FakeLlmProvider 集成：llm_provider.chat 被调用次数 == sub_task 数
8. 无 llm_provider：executor 不抛错
9. 并发跑：case_id 顺序与输入一致
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from kivi_agent.eval.team.models import (
    TeamCase,
    TeamDataset,
    TeamEvalResult,
)
from kivi_agent.eval.team.team_runner import TeamRunner
from tests._fakes import FakeLlmProvider, LlmScriptedResponse


# 写 JSONL fixture helper
def _write_team_cases(path: Path, cases: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


# 一个最小 case 工厂：researcher + writer
def _basic_case(case_id: str = "t1") -> TeamCase:
    """构造 2 成员 + 2 子任务的基本 case。"""
    return TeamCase(
        id=case_id,
        goal="research and summarize",
        member_specs=[
            {"name": "alice", "role": "researcher", "prompt": "search X"},
            {"name": "bob", "role": "writer", "prompt": "write"},
        ],
        sub_tasks=[
            {"assignee": "alice", "topic": "X research"},
            {"assignee": "bob", "topic": "summarize"},
        ],
        expected_assignments={"alice": 1, "bob": 1},
        expected_total_messages=2,
        max_steps_per_member=10,
    )


# 功能：run_case 跑通单个 case 并返回正确填充的 TeamEvalResult
# 设计：1 个 case → run_case → 断言 success=True、2 个 member_outcomes、
#       2 条 delegation_chain、events 含 team.created/finished
async def test_run_case_returns_populated_team_result() -> None:
    runner = TeamRunner(concurrency=1, llm_provider=None)
    case = _basic_case("t1")

    result = await runner.run_case(case)

    assert isinstance(result, TeamEvalResult)
    assert result.team_id.startswith("team-")
    assert result.success is True
    assert result.error is None
    # 2 个成员，每个都成功
    assert len(result.member_outcomes) == 2
    assert {m.name for m in result.member_outcomes} == {"alice", "bob"}
    assert all(m.success for m in result.member_outcomes)
    # 2 条委派步骤
    assert len(result.delegation_chain) == 2
    assignees = {s.to_member for s in result.delegation_chain}
    assert assignees == {"alice", "bob"}
    # 事件流：team.created + 2 个 member_dispatched + 2 个 handoff + team.finished
    event_types = [e.type for e in result.events]
    assert event_types[0] == "team.created"
    assert event_types[-1] == "team.finished"
    assert "team.member_dispatched" in event_types
    assert "team.handoff" in event_types
    # planned == actual（executor 严格按 case 委派）
    assert result.planned_assignments == {"alice": 1, "bob": 1}
    assert result.actual_assignments == {"alice": 1, "bob": 1}


# 功能：run_dataset 并发跑多 case 且顺序与输入一致
# 设计：3 个 case 写 JSONL → 加载 → run_dataset → 断言顺序 + 全成功
async def test_run_dataset_concurrent_preserves_order(tmp_path: Path) -> None:
    p = tmp_path / "team.jsonl"
    _write_team_cases(p, [
        {
            "id": f"t{i}",
            "goal": f"goal {i}",
            "member_specs": [{"name": "alice", "role": "researcher"}],
            "sub_tasks": [{"assignee": "alice", "topic": f"t{i}"}],
        }
        for i in range(3)
    ])
    ds = TeamDataset.load(p)
    runner = TeamRunner(concurrency=2, llm_provider=None)

    results = await runner.run_dataset(ds)

    assert len(results) == 3
    # 顺序保持：asyncio.gather 按入参顺序返回
    assert [r.goal for r in results] == [f"goal {i}" for i in range(3)]
    assert all(r.success for r in results)


# 功能：单 case 执行异常被隔离为 success=False，不阻塞其他 case
# 设计：patch execute_case，仅 id="bad" 抛错；其他 case 走原 executor；
#       断言 bad 失败 + 其他成功 + error 字段 + team.finished 事件
async def test_run_dataset_isolates_case_failure() -> None:
    case_a = _basic_case("ok-a")
    case_bad = _basic_case("bad")
    case_b = _basic_case("ok-b")
    ds = TeamDataset(name="mixed", cases=[case_a, case_bad, case_b])
    runner = TeamRunner(concurrency=2, llm_provider=None)

    from kivi_agent.eval.team.team_runner import execute_case as real_execute

    async def _execute_with_failure(
        case: TeamCase, llm_provider: Any = None, **kwargs: Any
    ) -> TeamEvalResult:
        if case.id == "bad":
            raise RuntimeError("synthetic team failure")
        return await real_execute(case, llm_provider, **kwargs)

    with patch(
        "kivi_agent.eval.team.team_runner.execute_case",
        new=AsyncMock(side_effect=_execute_with_failure),
    ):
        results = await runner.run_dataset(ds)

    assert len(results) == 3
    # 顺序保持：bad 在中间
    assert [r.goal for r in results] == [
        "research and summarize",
        "research and summarize",
        "research and summarize",
    ]
    # bad 失败、其它成功
    assert [r.success for r in results] == [True, False, True]
    failed = results[1]
    assert failed.error == "synthetic team failure"
    assert failed.finished_at is not None
    assert failed.events[-1].type == "team.finished"
    assert failed.events[-1].data["success"] is False


# 功能：每个 sub_task 都产生一条 DelegationStep（from=team, to=assignee）
# 设计：3 个 sub_task 委派给 2 成员；assert 委派链长度 = 3，from 全为 "team"
async def test_delegation_chain_one_step_per_subtask() -> None:
    case = TeamCase(
        id="t1",
        goal="multi",
        member_specs=[
            {"name": "alice", "role": "researcher"},
            {"name": "bob", "role": "writer"},
        ],
        sub_tasks=[
            {"assignee": "alice", "topic": "A"},
            {"assignee": "alice", "topic": "B"},
            {"assignee": "bob", "topic": "C"},
        ],
        expected_assignments={"alice": 2, "bob": 1},
    )
    runner = TeamRunner(concurrency=1, llm_provider=None)

    result = await runner.run_case(case)

    assert len(result.delegation_chain) == 3
    # 每步的 from_member 必为 "team"
    assert all(s.from_member == "team" for s in result.delegation_chain)
    # 委派给 alice 的有 2 步，bob 的有 1 步
    to_counts: dict[str, int] = {}
    for s in result.delegation_chain:
        to_counts[s.to_member] = to_counts.get(s.to_member, 0) + 1
    assert to_counts == {"alice": 2, "bob": 1}
    # planned/actual 一致
    assert result.planned_assignments == {"alice": 2, "bob": 1}
    assert result.actual_assignments == {"alice": 2, "bob": 1}


# 功能：mailbox tracker 计数正确：total_messages == successful_messages == sub_task 数
# 设计：2 个 sub_task 委派 → 每个成员消费 1 条 mailbox → total=2
async def test_mailbox_tracker_counts_match_subtask_count() -> None:
    case = _basic_case("t1")
    runner = TeamRunner(concurrency=1, llm_provider=None)

    result = await runner.run_case(case)

    # 2 个 sub_task → 2 个成员的 mailbox 各 1 条
    assert result.total_messages == 2
    assert result.successful_messages == 2


# 功能：委派给不存在的成员时记 team.unassigned 事件，不计入 actual
# 设计：1 个有效 sub_task + 1 个 unknown assignee；assert unassigned 事件 +
#       actual 不含 unknown
async def test_unassigned_subtask_emits_event_and_skips() -> None:
    case = TeamCase(
        id="t1",
        goal="partial",
        member_specs=[{"name": "alice", "role": "researcher"}],
        sub_tasks=[
            {"assignee": "alice", "topic": "valid"},
            {"assignee": "ghost", "topic": "orphan"},
        ],
    )
    runner = TeamRunner(concurrency=1, llm_provider=None)

    result = await runner.run_case(case)

    # 1 个有效委派 + 1 个 unassigned 事件
    assert len(result.delegation_chain) == 1
    unassigned = [e for e in result.events if e.type == "team.unassigned"]
    assert len(unassigned) == 1
    assert unassigned[0].data["assignee"] == "ghost"
    # actual 只含有效委派
    assert result.actual_assignments == {"alice": 1}
    assert result.planned_assignments == {"alice": 1, "ghost": 1}


# 功能：FakeLlmProvider 集成：chat() 被调用的次数 == sub_task 数
# 设计：3 sub_task + FakeLlmProvider → run_case → llm.call_count == 3
async def test_fake_llm_provider_called_per_subtask() -> None:
    case = TeamCase(
        id="t1",
        goal="multi",
        member_specs=[
            {"name": "alice", "role": "researcher"},
            {"name": "bob", "role": "writer"},
        ],
        sub_tasks=[
            {"assignee": "alice", "topic": "A"},
            {"assignee": "alice", "topic": "B"},
            {"assignee": "bob", "topic": "C"},
        ],
    )
    llm = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text=f"resp{i}") for i in range(3)],
    )
    runner = TeamRunner(concurrency=1, llm_provider=llm)

    result = await runner.run_case(case)

    assert llm.call_count == 3
    assert result.success is True


# 功能：llm_provider=None 时 executor 不抛错，正常跑完
# 设计：传 None → run_case → assert success=True（与默认行为一致）
async def test_executor_works_without_llm_provider() -> None:
    case = _basic_case("t1")
    runner = TeamRunner(concurrency=1, llm_provider=None)

    result = await runner.run_case(case)

    assert result.success is True
    assert result.error is None


# 功能：LLM 异常被吞掉，不影响 team 跑通
# 设计：FakeLlmProvider 每次 chat 都抛错；run_case 仍 success=True
async def test_llm_exception_is_swallowed_by_executor() -> None:
    case = _basic_case("t1")

    class _ExplodingLlm:
        async def chat(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("LLM exploded")

    runner = TeamRunner(concurrency=1, llm_provider=_ExplodingLlm())  # type: ignore[arg-type]

    result = await runner.run_case(case)

    assert result.success is True
    assert result.error is None


# 功能：run_dataset 高并发时 5 个 case 仍顺序保持
# 设计：5 个 case + concurrency=3 → 断言顺序 + 全成功
async def test_run_dataset_high_concurrency_preserves_order(tmp_path: Path) -> None:
    p = tmp_path / "team.jsonl"
    _write_team_cases(p, [
        {
            "id": f"c{i}",
            "goal": f"goal-{i}",
            "member_specs": [{"name": "alice", "role": "researcher"}],
            "sub_tasks": [{"assignee": "alice", "topic": f"t{i}"}],
        }
        for i in range(5)
    ])
    ds = TeamDataset.load(p)
    runner = TeamRunner(concurrency=3, llm_provider=None)

    results = await runner.run_dataset(ds)

    assert len(results) == 5
    assert [r.goal for r in results] == [f"goal-{i}" for i in range(5)]


# 功能：成员 steps 受 max_steps_per_member 限制；超限时 success=False
# 设计：10 sub_task 全给 alice + max_steps=3；assert alice.success=False
async def test_member_success_bounded_by_max_steps() -> None:
    case = TeamCase(
        id="t1",
        goal="overload",
        member_specs=[{"name": "alice", "role": "researcher"}],
        sub_tasks=[{"assignee": "alice", "topic": f"t{i}"} for i in range(10)],
        max_steps_per_member=3,
    )
    runner = TeamRunner(concurrency=1, llm_provider=None)

    result = await runner.run_case(case)

    alice = next(m for m in result.member_outcomes if m.name == "alice")
    # steps 累加到 10，超过 max_steps=3
    assert alice.steps == 10
    assert alice.success is False
    # team.success 跟随 member.success
    assert result.success is False
