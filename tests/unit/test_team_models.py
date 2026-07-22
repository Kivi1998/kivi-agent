from __future__ import annotations

from kivi_agent.core.teams.models import AgentTeam, TeammateInfo


# 功能：验证 TeammateInfo 用最小字段构造时 status 默认是 "pending"
# 设计：团队刚创建、后台任务还没跑完时的默认状态，供后续状态查询工具做初始展示
def test_teammate_info_defaults_to_pending() -> None:
    member = TeammateInfo(name="planner", role="planner", run_id="run-1")
    assert member.status == "pending"


# 功能：验证 AgentTeam 能持有多个成员并按名字查找
# 设计：team_status/team_message 工具都需要按名字定位到具体成员，覆盖这个查找路径
def test_agent_team_find_member_by_name() -> None:
    team = AgentTeam(id="team-1", goal="重构登录模块", members=[
        TeammateInfo(name="planner", role="planner", run_id="run-1"),
        TeammateInfo(name="executor", role="executor", run_id="run-2"),
    ])
    found = team.find_member("executor")
    assert found is not None
    assert found.run_id == "run-2"
    assert team.find_member("nonexistent") is None
