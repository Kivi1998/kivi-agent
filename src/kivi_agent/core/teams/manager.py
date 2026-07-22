from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from kivi_agent.core.bus.events import TeamCreatedEvent
from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.subagent.registry import BackgroundTaskRegistry
from kivi_agent.core.subagent.tool import spawn_background_subagent
from kivi_agent.core.teams.models import AgentTeam, TeammateInfo

if TYPE_CHECKING:
    from kivi_agent.core.llm.base import LLMProvider
    from kivi_agent.core.permissions.manager import PermissionManager


class TeamManager:
    # 初始化团队管理器，持有创建子 agent 所需的全部依赖（与 SpawnAgentTool 构造参数一致）
    def __init__(
        self,
        *,
        provider: LLMProvider | None,
        bus: EventBus,
        permission_manager: PermissionManager | None,
        max_steps: int,
        task_registry: BackgroundTaskRegistry,
        runs_dir: Path,
        session_id: str,
    ) -> None:
        self._provider = provider
        self._bus = bus
        self._permission_manager = permission_manager
        self._max_steps = max_steps
        self._task_registry = task_registry
        self._runs_dir = runs_dir
        self._session_id = session_id
        self._teams: dict[str, AgentTeam] = {}

    # 为每次 run 重新绑定 per-run 的 provider/bus/session_id；teams 状态保持不变
    def bind(
        self,
        *,
        provider: LLMProvider,
        bus: EventBus,
        session_id: str,
    ) -> None:
        self._provider = provider
        self._bus = bus
        self._session_id = session_id

    # 为每个 member_spec 创建一个后台子 agent，组装成一个 AgentTeam 并保存
    async def create_team(self, goal: str, member_specs: list[dict[str, str]]) -> AgentTeam:
        if self._provider is None:
            raise RuntimeError("TeamManager.bind() must be called before create_team()")
        team_id = f"team-{uuid.uuid4().hex[:8]}"
        members: list[TeammateInfo] = []
        for spec in member_specs:
            run_id = await spawn_background_subagent(
                provider=self._provider, parent_bus=self._bus, parent_run_id=team_id,
                permission_manager=self._permission_manager, max_steps=self._max_steps,
                task_registry=self._task_registry, runs_dir=self._runs_dir,
                session_id=self._session_id, depth=0,
                description=f"team member: {spec['name']}", prompt=spec["prompt"],
                subagent_type=spec.get("role", ""),
            )
            members.append(TeammateInfo(name=spec["name"], role=spec.get("role", ""), run_id=run_id))
        team = AgentTeam(id=team_id, goal=goal, members=members)
        self._teams[team_id] = team
        await self._bus.publish(
            TeamCreatedEvent(
                team_id=team.id,
                goal=team.goal,
                members=[{"name": m.name, "role": m.role, "run_id": m.run_id} for m in team.members],
                ts=datetime.now(UTC).isoformat(),
            )
        )
        return team

    # 按 team_id 查找团队；不存在返回 None
    def get_team(self, team_id: str) -> AgentTeam | None:
        return self._teams.get(team_id)
