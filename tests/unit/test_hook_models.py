from __future__ import annotations

from kama_claude.core.hooks.events import LifecycleEvent
from kama_claude.core.hooks.models import Hook


# 功能：验证 Hook 能用最小必填字段构造，可选字段有合理默认值
# 设计：只传 id/event/command，断言 reject 默认为 False、async_exec 默认为 False，
#      确保新增字段不会破坏最简单的钩子定义
def test_hook_minimal_construction_has_safe_defaults() -> None:
    hook = Hook(id="h1", event=LifecycleEvent.PRE_TOOL_USE, command="echo pre")
    assert hook.reject is False
    assert hook.async_exec is False
    assert hook.condition is None


# 功能：验证 LifecycleEvent 至少包含工具调用前后两个核心事件类型
# 设计：这两个类型是 Task D6 HookEngine 唯一会用到的，先在这里锁定字符串值不被后续误改
def test_lifecycle_event_has_tool_hooks() -> None:
    assert LifecycleEvent.PRE_TOOL_USE.value == "pre_tool_use"
    assert LifecycleEvent.POST_TOOL_USE.value == "post_tool_use"
