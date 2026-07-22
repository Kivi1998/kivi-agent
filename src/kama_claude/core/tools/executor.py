from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from kama_claude.core.llm.types import ToolCallBlock
from kama_claude.core.tools.invocation import invoke_tool
from kama_claude.core.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from kama_claude.core.events.bus import EventBus
    from kama_claude.core.hooks.engine import HookEngine
    from kama_claude.core.permissions.manager import PermissionManager
    from kama_claude.core.tools.base import ToolResult


# 按 category 把连续的只读（"read"）工具调用分进同一批次；遇到非只读或未知工具单独成批
def partition_tool_calls(
    tool_calls: list[ToolCallBlock], registry: ToolRegistry
) -> list[list[ToolCallBlock]]:
    batches: list[list[ToolCallBlock]] = []
    current_read_batch: list[ToolCallBlock] = []

    for tc in tool_calls:
        tool = registry.get(tc.name)
        is_read = tool is not None and tool.category == "read"
        if is_read:
            current_read_batch.append(tc)
        else:
            if current_read_batch:
                batches.append(current_read_batch)
                current_read_batch = []
            batches.append([tc])

    if current_read_batch:
        batches.append(current_read_batch)

    return batches


# 依次执行每个批次：批内工具调用并发跑（asyncio.gather），批与批之间串行，保持工具调用整体顺序稳定
async def execute_tool_batches(
    batches: list[list[ToolCallBlock]],
    registry: ToolRegistry,
    bus: EventBus,
    run_id: str,
    *,
    permission_manager: PermissionManager | None = None,
    session_id: str = "",
    hook_engine: HookEngine | None = None,
) -> list[tuple[ToolCallBlock, ToolResult]]:
    results: list[tuple[ToolCallBlock, ToolResult]] = []
    for batch in batches:
        batch_results = await asyncio.gather(*[
            invoke_tool(
                registry, tc, bus, run_id,
                permission_manager=permission_manager,
                session_id=session_id,
                hook_engine=hook_engine,
            )
            for tc in batch
        ])
        results.extend(zip(batch, batch_results, strict=True))
    return results
