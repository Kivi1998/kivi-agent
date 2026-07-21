from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from kama_claude.core.events.bus import EventBus
from kama_claude.core.subagent.registry import BackgroundTaskRegistry
from kama_claude.core.teams.manager import TeamManager
from kama_claude.core.tools.builtin.team_status import TeamStatusTool


# 功能：验证查询一个刚创建、还在跑的团队时，每个成员状态显示为运行中而不是报错
# 设计：真实起了后台 asyncio.Task（还没被 await 完成），断言输出里包含每个成员名字和"running"类状态描述，
#      覆盖"团队还没完成时查询也应该给出有意义信息"这个场景
async def test_team_status_reports_running_members(tmp_path: Path) -> None:
    fake_provider = AsyncMock()

    async def _slow_chat(*args: object, **kwargs: object) -> object:
        await asyncio.sleep(10)  # 不会真的等完，测试里会在这之前查询状态
        return None

    fake_provider.chat.side_effect = _slow_chat

    task_registry = BackgroundTaskRegistry()
    manager = TeamManager(
        provider=fake_provider, bus=EventBus(), permission_manager=None,
        max_steps=5, task_registry=task_registry, runs_dir=tmp_path, session_id="sess-1",
    )
    team = await manager.create_team(goal="g", member_specs=[{"name": "a", "role": "executor", "prompt": "p"}])

    tool = TeamStatusTool(manager)
    result = await tool.invoke({"team_id": team.id})
    assert not result.is_error
    assert "a" in result.content
    assert "running" in result.content.lower()


# 功能：验证查询不存在的 team_id 返回明确错误而不是抛异常
# 设计：覆盖"team_id 打错了"这个用户输入错误场景
async def test_team_status_unknown_team_returns_error(tmp_path: Path) -> None:
    manager = TeamManager(
        provider=MagicMock(), bus=EventBus(), permission_manager=None,
        max_steps=5, task_registry=BackgroundTaskRegistry(), runs_dir=tmp_path, session_id="sess-1",
    )
    tool = TeamStatusTool(manager)
    result = await tool.invoke({"team_id": "nonexistent"})
    assert result.is_error
