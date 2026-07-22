from __future__ import annotations

from kivi_agent.core.hooks.engine import HookEngine
from kivi_agent.core.hooks.events import LifecycleEvent
from kivi_agent.core.hooks.models import Hook
from kivi_agent.core.tools.errors import ToolRejectedError


# 功能：验证 reject=True 的钩子命令返回非零退出码时，run_pre_tool_hooks 抛出 ToolRejectedError
# 设计：用一个必然失败的 shell 命令（exit 1）模拟"钩子否决"，断言异常类型和消息包含工具名，
#      确保调用方能据此把工具调用短路掉
async def test_pre_hook_reject_raises() -> None:
    engine = HookEngine([
        Hook(id="deny-all", event=LifecycleEvent.PRE_TOOL_USE, command="exit 1", reject=True)
    ])
    try:
        await engine.run_pre_tool_hooks("bash", {"command": "rm -rf /"})
        raise AssertionError("expected ToolRejectedError")
    except ToolRejectedError as exc:
        assert "deny-all" in str(exc)


# 功能：验证 reject=False 的钩子即使命令失败也不会阻断，只是被忽略（记日志，不抛异常）
# 设计：同样用 exit 1 但 reject=False，断言 run_pre_tool_hooks 正常返回不抛异常，
#      覆盖"钩子失败默认不影响主流程"这条设计原则
async def test_non_reject_hook_failure_is_swallowed() -> None:
    engine = HookEngine([
        Hook(id="noisy", event=LifecycleEvent.PRE_TOOL_USE, command="exit 1", reject=False)
    ])
    await engine.run_pre_tool_hooks("bash", {"command": "echo hi"})  # 不应抛异常
