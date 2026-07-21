from __future__ import annotations

from dataclasses import dataclass

from kama_claude.core.hooks.events import LifecycleEvent


@dataclass
class Hook:
    id: str
    event: LifecycleEvent
    command: str
    # 可选的 shell 表达式，为空字符串外的求值失败/为 false 时跳过该钩子
    condition: str | None = None
    # True 时钩子返回非零退出码会阻断对应的工具调用（仅 PRE_TOOL_USE 有意义）
    reject: bool = False
    # True 时钩子在后台异步执行，不阻塞主流程等待其完成
    async_exec: bool = False
