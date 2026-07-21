from __future__ import annotations

from kama_claude.core.agents.loader import AgentProfileLoader


# 功能：验证内建 coordinator 角色的 allowed_tools 不含任何写操作工具（write_file/edit_file/bash）
# 设计："协调者只调度不编码"这个约束的验收标准就是白名单里没有写类工具，
#      覆盖配置文件本身而不是运行时行为——运行时行为已经由 _build_child_registry 的
#      _allowed() 过滤机制保证，这里只需确认配置内容正确
def test_coordinator_profile_excludes_write_tools() -> None:
    loader = AgentProfileLoader()
    profile = loader.load("coordinator")
    assert profile is not None
    forbidden = {"write_file", "edit_file", "bash"}
    assert forbidden.isdisjoint(set(profile.allowed_tools))
    assert "team_create" in profile.allowed_tools
    assert "team_message" in profile.allowed_tools
