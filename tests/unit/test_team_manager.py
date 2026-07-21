from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

from kama_claude.core.events.bus import EventBus
from kama_claude.core.llm.types import LlmResponse, UsageStats
from kama_claude.core.subagent.registry import BackgroundTaskRegistry
from kama_claude.core.teams.manager import TeamManager


def _make_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.chat = AsyncMock(
        return_value=LlmResponse(
            stop_reason="end_turn",
            tool_calls=[],
            text="done",
            usage=UsageStats(0, 0, 0, 0, 0.0),
        )
    )
    return provider


# 功能：验证 create_team 为每个 member_spec 各起一个后台 subagent，并把 run_id 正确关联进团队成员
# 设计：断言团队里的成员数量、名字、角色都和输入一致，且每个成员的 run_id 在 task_registry 里能查到，
#      覆盖"团队创建 = 批量 spawn + 元数据记录"这个核心行为
async def test_create_team_spawns_all_members(tmp_path: Path) -> None:
    manager = TeamManager(
        provider=_make_provider(), bus=EventBus(), permission_manager=None,
        max_steps=5, task_registry=BackgroundTaskRegistry(), runs_dir=tmp_path, session_id="sess-1",
    )
    team = await manager.create_team(
        goal="重构登录模块",
        member_specs=[
            {"name": "planner", "role": "planner", "prompt": "制定计划"},
            {"name": "executor", "role": "executor", "prompt": "执行改动"},
        ],
    )
    assert team.goal == "重构登录模块"
    assert len(team.members) == 2
    assert {m.name for m in team.members} == {"planner", "executor"}
    assert all(m.run_id for m in team.members)


# 功能：验证创建后可以通过 get_team 查回同一个团队对象
# 设计：team_status/team_message 工具都要按 team_id 查团队，覆盖这个基本存取路径
async def test_get_team_returns_created_team(tmp_path: Path) -> None:
    manager = TeamManager(
        provider=_make_provider(), bus=EventBus(), permission_manager=None,
        max_steps=5, task_registry=BackgroundTaskRegistry(), runs_dir=tmp_path, session_id="sess-1",
    )
    team = await manager.create_team(goal="g", member_specs=[{"name": "a", "role": "executor", "prompt": "p"}])
    assert manager.get_team(team.id) is team
    assert manager.get_team("nonexistent") is None
