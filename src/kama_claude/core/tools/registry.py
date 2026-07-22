from __future__ import annotations

from kama_claude.core.tools.base import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._deferred: set[str] = set()
        self._discovered: set[str] = set()

    # 注册工具；deferred=True 时该工具默认不出现在 tool_schemas()，需先被 mark_discovered
    def register(self, tool: BaseTool, *, deferred: bool = False) -> None:
        self._tools[tool.name] = tool
        if deferred:
            self._deferred.add(tool.name)
        else:
            self._deferred.discard(tool.name)

    # 按名称查找工具，不存在返回 None（无论是否 deferred，都能直接查到）
    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    # 把一个 deferred 工具标记为已发现，之后会出现在 tool_schemas() 里
    def mark_discovered(self, name: str) -> None:
        self._discovered.add(name)

    # 返回当前应该暴露给 LLM 的工具 schema：非 deferred 工具 + 已发现的 deferred 工具
    def tool_schemas(self) -> list[dict[str, object]]:
        visible = [
            tool for name, tool in self._tools.items()
            if name not in self._deferred or name in self._discovered
        ]
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in visible
        ]

    # 按关键词搜索工具（不受 deferred 状态影响，搜索本身就是发现机制的一部分）：
    # 名字命中权重高于描述命中，按分数降序返回最多 limit 个
    def search(self, query: str, limit: int = 5) -> list[BaseTool]:
        q = query.strip().lower()
        if not q:
            return []
        scored: list[tuple[int, BaseTool]] = []
        for tool in self._tools.values():
            score = 0
            if q in tool.name.lower():
                score += 10
            if q in tool.description.lower():
                score += 5
            if score > 0:
                scored.append((score, tool))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [tool for _, tool in scored[:limit]]
