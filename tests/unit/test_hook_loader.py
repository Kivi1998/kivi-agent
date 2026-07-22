from __future__ import annotations

from kivi_agent.core.config import HookEntry, HooksConfig
from kivi_agent.core.hooks.events import LifecycleEvent
from kivi_agent.core.hooks.loader import load_hooks


# 功能：验证 HooksConfig 里的条目能正确转换成 Hook 对象列表
# 设计：构造一个含单条 hook 配置的 HooksConfig，断言转换后的字段一一对应，
#      覆盖"配置层 → 领域对象"这层薄转换的正确性
def test_load_hooks_converts_config_entries() -> None:
    config = HooksConfig(entries=[
        HookEntry(id="fmt", event="post_tool_use", command="ruff format", reject=False, async_exec=True)
    ])
    hooks = load_hooks(config)
    assert len(hooks) == 1
    assert hooks[0].id == "fmt"
    assert hooks[0].event == LifecycleEvent.POST_TOOL_USE
    assert hooks[0].async_exec is True
