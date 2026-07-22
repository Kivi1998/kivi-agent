from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from kama_claude.core.tools.base import BaseTool, ToolResult
from kama_claude.core.tools.registry import ToolRegistry


class ToolSearchParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str


class ToolSearchTool(BaseTool):
    params_model = ToolSearchParams
    name = "tool_search"
    category = "read"
    description = (
        "Search for additional tools by keyword when the tool you need isn't in your "
        "current tool list. Matching tools become available for you to call immediately."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Keyword to search for."}},
        "required": ["query"],
    }

    # 注入 registry，用于搜索并标记发现的工具
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    # 搜索匹配工具，标记为已发现，返回名字+描述列表
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = ToolSearchParams.model_validate(params)
        results = self._registry.search(p.query)
        if not results:
            return ToolResult(content=f"no tools found matching: {p.query}")
        for tool in results:
            self._registry.mark_discovered(tool.name)
        lines = [f"{t.name}: {t.description}" for t in results]
        return ToolResult(content="\n".join(lines))
