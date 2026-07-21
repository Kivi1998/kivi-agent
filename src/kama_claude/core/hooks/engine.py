from __future__ import annotations

import asyncio
import json
import logging

from kama_claude.core.hooks.events import LifecycleEvent
from kama_claude.core.hooks.models import Hook
from kama_claude.core.tools.errors import ToolRejectedError

logger = logging.getLogger(__name__)
_HOOK_TIMEOUT_S = 10.0


class HookEngine:
    # 初始化钩子引擎，持有全部已配置钩子的列表
    def __init__(self, hooks: list[Hook]) -> None:
        self._hooks = hooks

    # 返回指定生命周期事件下配置的钩子，保持配置顺序
    def _hooks_for(self, event: LifecycleEvent) -> list[Hook]:
        return [h for h in self._hooks if h.event == event]

    # 以 shell 子进程执行一个钩子命令，返回退出码；超时或异常按失败处理（退出码 1）
    async def _run_command(self, command: str, payload: dict[str, object]) -> int:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            payload_bytes = json.dumps(payload).encode("utf-8")
            await asyncio.wait_for(proc.communicate(payload_bytes), timeout=_HOOK_TIMEOUT_S)
            return proc.returncode or 0
        except Exception:
            logger.exception("hook command failed: %s", command)
            return 1

    # 依次执行工具调用前的钩子；任一 reject=True 的钩子返回非零退出码则抛出 ToolRejectedError
    async def run_pre_tool_hooks(self, tool_name: str, params: dict[str, object]) -> None:
        payload: dict[str, object] = {
            "event": LifecycleEvent.PRE_TOOL_USE.value,
            "tool_name": tool_name,
            "params": params,
        }
        for hook in self._hooks_for(LifecycleEvent.PRE_TOOL_USE):
            code = await self._run_command(hook.command, payload)
            if code != 0:
                if hook.reject:
                    raise ToolRejectedError(
                        f"tool call rejected by hook '{hook.id}' (exit code {code})"
                    )
                logger.warning(
                    "non-blocking pre_tool_use hook '%s' failed (exit code %d)",
                    hook.id,
                    code,
                )

    # 触发工具调用后的钩子；async_exec=True 的钩子后台执行不等待，其余顺序等待完成
    async def run_post_tool_hooks(self, tool_name: str, result_summary: str) -> None:
        payload: dict[str, object] = {
            "event": LifecycleEvent.POST_TOOL_USE.value,
            "tool_name": tool_name,
            "result_summary": result_summary,
        }
        for hook in self._hooks_for(LifecycleEvent.POST_TOOL_USE):
            if hook.async_exec:
                asyncio.ensure_future(self._run_command(hook.command, payload))
            else:
                await self._run_command(hook.command, payload)
