from __future__ import annotations

from enum import StrEnum

from kivi_agent.core.permissions.policy import PermissionDecision


class PermissionMode(StrEnum):
    DEFAULT = "default"
    ACCEPT_EDITS = "accept_edits"
    PLAN = "plan"
    BYPASS = "bypass"


# 按当前权限模式和工具分类返回强制决策；None 表示该模式对此分类不干预，交给原有分层策略决定
def mode_override(mode: PermissionMode, category: str) -> PermissionDecision | None:
    if mode == PermissionMode.BYPASS:
        return PermissionDecision.ALLOW
    if mode == PermissionMode.PLAN:
        if category in ("write", "command"):
            return PermissionDecision.DENY
        return None
    if mode == PermissionMode.ACCEPT_EDITS:
        if category == "write":
            return PermissionDecision.ALLOW
        return None
    return None
