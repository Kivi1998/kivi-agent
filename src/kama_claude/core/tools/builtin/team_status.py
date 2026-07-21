from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from kama_claude.core.teams.manager import TeamManager
from kama_claude.core.tools.base import BaseTool, ToolResult


class TeamStatusParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    team_id: str


class TeamStatusTool(BaseTool):
    params_model = TeamStatusParams
    name = "team_status"
    category = "read"
    description = "Check the progress of all members in a team created by team_create."
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {"team_id": {"type": "string"}},
        "required": ["team_id"],
    }

    # 注入 TeamManager，用于按 team_id 查询团队和各成员的后台任务状态
    def __init__(self, team_manager: TeamManager) -> None:
        self._team_manager = team_manager

    # 汇总团队每个成员的后台任务状态，返回可读的进度摘要
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = TeamStatusParams.model_validate(params)
        team = self._team_manager.get_team(p.team_id)
        if team is None:
            return ToolResult(
                content=f"unknown team_id: {p.team_id}", is_error=True, error_type="runtime_error"
            )

        lines = [f"team {team.id}: {team.goal}"]
        for member in team.members:
            entry = self._team_manager._task_registry.get(member.run_id)
            if entry is None:
                status = "unknown"
            else:
                task, _ = entry
                done = task.done()
                if not done:
                    status = "running"
                else:
                    status = "failed" if task.exception() else "success"
            lines.append(f"  - {member.name} ({member.role}): {status}")
        return ToolResult(content="\n".join(lines))
