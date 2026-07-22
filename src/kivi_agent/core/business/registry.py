"""业务 Tool 注册表（agent: package-c-v1）。

演示版：模块级单例 + 简单 dict 即可；不需要走 BaseTool 的 deferred / mark_discovered
机制，因为业务 Tool 都是默认对外可见的（由 Runner 在 _build_registry() 末尾
按 tool_whitelist 选择性注册到 kivi-agent 的 ToolRegistry）。

未来扩展：当业务 Tool 数量 > 20 或需要自动发现（按配置文件加载）时，可改造
为类似 ToolRegistry 的实现。
"""

from __future__ import annotations

from kivi_agent.core.business.base import BaseBusinessTool


# 业务 Tool 注册表（agent: package-c-v1）
class BusinessToolRegistry:
    """业务 Tool 命名空间注册表。

    与 kivi_agent.core.tools.registry.ToolRegistry 的区别：
    - 只管业务 Tool，不混入内置 Tool
    - 演示版不做 deferred / discovery 机制（业务 Tool 数量少且都默认可见）
    - 用于内部依赖注入、单元测试解耦，不直接交给 LLM
    """

    def __init__(self) -> None:
        # tool_name -> BaseBusinessTool 实例
        self._tools: dict[str, BaseBusinessTool] = {}

    # 注册一个业务 Tool；同名重复注册会覆盖（演示版简单策略）
    def register(self, tool: BaseBusinessTool) -> None:
        self._tools[tool.name] = tool

    # 按名称查找业务 Tool；不存在返回 None
    def get(self, name: str) -> BaseBusinessTool | None:
        return self._tools.get(name)

    # 返回所有已注册业务 Tool 的名称列表（按字母排序，便于测试断言）
    def list_names(self) -> list[str]:
        return sorted(self._tools.keys())

    # 返回所有已注册业务 Tool 实例列表（按名称排序）
    def list_all(self) -> list[BaseBusinessTool]:
        return [self._tools[name] for name in self.list_names()]

    # 移除一个业务 Tool（主要用于测试 teardown；演示版一般不调用）
    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    # 清空全部（仅用于测试 teardown）
    def clear(self) -> None:
        self._tools.clear()


# 业务 Tool 注册表模块级单例（agent: package-c-v1）
# 演示版用模块级单例足以；Runner 不直接 import 它，而是显式构造 6 个 Tool 后
# 调 ToolRegistry.register。本单例留给业务 Tool 之间互相引用（如未来
# memory_recall 需要 memory_save 反查时）。
business_tool_registry = BusinessToolRegistry()
