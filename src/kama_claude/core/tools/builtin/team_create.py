from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from kama_claude.core.teams.manager import TeamManager
from kama_claude.core.tools.base import BaseTool, ToolResult


class MemberSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    role: str = ""
    prompt: str


class TeamCreateParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    goal: str
    members: list[MemberSpec]


class TeamCreateTool(BaseTool):
    params_model = TeamCreateParams
    name = "team_create"
    category = "other"
    description = (
        "Create a team of background sub-agents that work in parallel toward a shared goal. "
        "Each member gets its own prompt and optional role (planner/executor/reviewer). "
        "Members run independently — use team_message to coordinate between them and "
        "team_status to check overall progress."
    )
    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "Overall goal the team is working toward."},
            "members": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "role": {"type": "string", "description": "planner|executor|reviewer|coordinator"},
                        "prompt": {"type": "string"},
                    },
                    "required": ["name", "prompt"],
                },
            },
        },
        "required": ["goal", "members"],
    }

    # 注入 TeamManager，负责实际创建团队
    def __init__(self, team_manager: TeamManager) -> None:
        self._team_manager = team_manager

    # 创建团队并返回团队 ID 与各成员 run_id 摘要
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = TeamCreateParams.model_validate(params)
        team = await self._team_manager.create_team(
            p.goal, [m.model_dump() for m in p.members]
        )
        lines = [f"team_id={team.id}"] + [
            f"  - {m.name} ({m.role}): run_id={m.run_id}" for m in team.members
        ]
        return ToolResult(content="\n".join(lines))
