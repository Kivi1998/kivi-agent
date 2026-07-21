from __future__ import annotations

from kama_claude.core.permissions.modes import PermissionMode, mode_override
from kama_claude.core.permissions.policy import PermissionDecision


# 功能：验证 BYPASS 模式下任意分类的工具都被直接放行
# 设计：分别用 read/write/command 三种分类调用，断言全部返回 ALLOW，覆盖模式的"全放行"语义
def test_bypass_mode_allows_everything() -> None:
    for category in ("read", "write", "command"):
        assert mode_override(PermissionMode.BYPASS, category) == PermissionDecision.ALLOW


# 功能：验证 PLAN 模式下 write/command 类工具被直接拒绝，read 类工具不受模式干预
# 设计：write/command 断言 DENY（计划阶段不允许真正修改），read 断言 None（交给原有 policy 逻辑决定，通常是 ALLOW）
def test_plan_mode_blocks_write_and_command_only() -> None:
    assert mode_override(PermissionMode.PLAN, "write") == PermissionDecision.DENY
    assert mode_override(PermissionMode.PLAN, "command") == PermissionDecision.DENY
    assert mode_override(PermissionMode.PLAN, "read") is None


# 功能：验证 DEFAULT 模式完全不干预，任何分类都返回 None
# 设计：DEFAULT 是"不改变现有行为"的模式，None 表示"这一层没有意见，继续走原策略"
def test_default_mode_never_overrides() -> None:
    for category in ("read", "write", "command", "other"):
        assert mode_override(PermissionMode.DEFAULT, category) is None
