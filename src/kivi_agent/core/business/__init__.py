"""业务 Tool 子包（agent: package-c-v1）。

按 docs/contracts/v1.md §1 锁定的 6 个业务 Tool 名提供演示版 Mock 实现。
演示版 100% Mock，不依赖任何外部服务（Tavily / RAGFlow / 真实 DB / ECharts service）。
"""

# 业务 Tool 基类（agent: package-c-v1）
from kivi_agent.core.business.base import BaseBusinessTool

# 业务 Tool 注册表（agent: package-c-v1）
from kivi_agent.core.business.registry import BusinessToolRegistry, business_tool_registry

__all__ = [
    "BaseBusinessTool",
    "BusinessToolRegistry",
    "business_tool_registry",
]
