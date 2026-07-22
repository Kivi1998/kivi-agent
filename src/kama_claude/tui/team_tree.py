from __future__ import annotations

from textual.widgets import Static

from kama_claude.core.teams.models import AgentTeam, TeammateInfo


class TeamTreeState:
    # 初始化空的团队状态表，以及 run_id -> team_id 的反查索引（用于处理 subagent 事件时定位团队）
    def __init__(self) -> None:
        self.teams: dict[str, AgentTeam] = {}
        self._run_to_team: dict[str, str] = {}

    # 处理 team.created 事件：注册团队及全部成员，建立 run_id 反查索引
    def on_team_created(self, *, team_id: str, goal: str, members: list[dict[str, str]]) -> None:
        team_members = [
            TeammateInfo(name=m["name"], role=m["role"], run_id=m["run_id"]) for m in members
        ]
        self.teams[team_id] = AgentTeam(id=team_id, goal=goal, members=team_members)
        for m in team_members:
            self._run_to_team[m.run_id] = team_id

    # 处理 subagent.started 事件：把对应成员状态置为 running
    def on_subagent_started(self, *, run_id: str) -> None:
        self._update_member_status(run_id, "running")

    # 处理 subagent.finished 事件：把对应成员状态置为最终状态
    def on_subagent_finished(self, *, run_id: str, status: str) -> None:
        self._update_member_status(run_id, status)

    # 按 run_id 反查团队和成员，更新其状态；找不到（非团队成员的普通子 agent）时静默忽略
    def _update_member_status(self, run_id: str, status: str) -> None:
        team_id = self._run_to_team.get(run_id)
        if team_id is None:
            return
        team = self.teams[team_id]
        for member in team.members:
            if member.run_id == run_id:
                member.status = status
                return


_STATUS_ICON: dict[str, str] = {
    "pending": "○",
    "running": "◐",
    "success": "●",
    "failed": "✗",
}


class TeamTreeWidget(Static):
    """展示所有团队及其成员的实时状态树。"""

    # 初始化，持有共享的状态对象（由 KamaTuiApp 在事件分发时统一更新）
    def __init__(self, state: TeamTreeState) -> None:
        super().__init__()
        self._state = state

    # 根据当前状态重新渲染整棵树
    def refresh_tree(self) -> None:
        lines: list[str] = []
        for team in self._state.teams.values():
            lines.append(f"[bold]{team.id}[/bold]  {team.goal}")
            for member in team.members:
                icon = _STATUS_ICON.get(member.status, "?")
                lines.append(f"  {icon} {member.name} ({member.role})")
        self.update("\n".join(lines) if lines else "[dim]no teams yet[/dim]")
