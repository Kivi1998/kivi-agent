from __future__ import annotations

from kivi_agent.core.config import HooksConfig
from kivi_agent.core.hooks.events import LifecycleEvent
from kivi_agent.core.hooks.models import Hook


# 将配置层的 HooksConfig 转换成领域对象 Hook 列表
def load_hooks(config: HooksConfig) -> list[Hook]:
    return [
        Hook(
            id=entry.id,
            event=LifecycleEvent(entry.event),
            command=entry.command,
            condition=entry.condition,
            reject=entry.reject,
            async_exec=entry.async_exec,
        )
        for entry in config.entries
    ]
