from __future__ import annotations

from kama_claude.core.tools.builtin.tool_search import ToolSearchTool
from kama_claude.core.tools.builtin.write_file import WriteFileTool
from kama_claude.core.tools.registry import ToolRegistry


# 功能：验证调用 tool_search 后，匹配到的 deferred 工具被标记为已发现，随后出现在 tool_schemas 里
# 设计：这是"搜索即发现"这个约定的端到端验证——不只是返回搜索结果文本，
#      还要真的改变 registry 状态让工具变得可调用
async def test_tool_search_marks_results_as_discovered() -> None:
    registry = ToolRegistry()
    registry.register(WriteFileTool(), deferred=True)
    tool = ToolSearchTool(registry)

    result = await tool.invoke({"query": "write"})
    assert not result.is_error
    assert "write_file" in result.content
    assert "write_file" in {s["name"] for s in registry.tool_schemas()}
