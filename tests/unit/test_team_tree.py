from __future__ import annotations

from kama_claude.tui.team_tree import TeamTreeState


# 功能：验证收到 TeamCreatedEvent 后，状态里出现对应团队和全部成员，初始状态为 "pending"
# 设计：团队树的数据模型和事件订阅逻辑分离测试，不需要真的挂载 Textual 组件
def test_state_registers_team_on_created_event() -> None:
    state = TeamTreeState()
    state.on_team_created(
        team_id="team-1", goal="g",
        members=[{"name": "a", "role": "executor", "run_id": "run-1"}],
    )
    assert "team-1" in state.teams
    assert state.teams["team-1"].members[0].status == "pending"


# 功能：验证收到 SubagentStartedEvent/SubagentFinishedEvent 后，对应成员状态被更新
# 设计：按 run_id 匹配到具体成员并更新其 status，覆盖团队树"实时反映进度"这个核心价值
def test_state_updates_member_status_on_subagent_events() -> None:
    state = TeamTreeState()
    state.on_team_created(
        team_id="team-1", goal="g",
        members=[{"name": "a", "role": "executor", "run_id": "run-1"}],
    )
    state.on_subagent_started(run_id="run-1")
    assert state.teams["team-1"].find_member("a").status == "running"

    state.on_subagent_finished(run_id="run-1", status="success")
    assert state.teams["team-1"].find_member("a").status == "success"


# 功能：验证没有匹配到团队的 subagent 事件被静默忽略（不抛异常、不影响现有状态）
# 设计：普通子 agent（非团队成员）的 SubagentStartedEvent 也会出现在事件流里，
#      团队树不应该因此崩溃，覆盖"无关事件不污染团队树"这个隔离性需求
def test_state_ignores_subagent_events_for_unknown_runs() -> None:
    state = TeamTreeState()
    state.on_team_created(
        team_id="team-1", goal="g",
        members=[{"name": "a", "role": "executor", "run_id": "run-1"}],
    )
    state.on_subagent_started(run_id="run-orphan")
    state.on_subagent_finished(run_id="run-orphan", status="success")
    assert state.teams["team-1"].members[0].status == "pending"
