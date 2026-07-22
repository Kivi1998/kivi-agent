"""业务 Tool 基类（agent: package-c-v1）。

按 docs/contracts/v1.md 决议：6 个业务 Tool（web_search / rag_query / query_database /
echarts_render / memory_save / memory_recall）都继承自本基类，本基类再复用
kivi_agent.core.tools.base.BaseTool，避免直接耦合 kivi-agent 内置 Tool 体系。

为何需要独立基类：业务 Tool 的语义比内置 Tool 复杂——可能涉及运行时注入
（datasource_id / knowledge_base_id），并有统一的"演示版 Mock 模式"约定。
后续会通过本基类统一接入 Permission / Mock 开关 / 事件追踪等横切关注点。
"""

from __future__ import annotations

from typing import Any

from kivi_agent.core.tools.base import BaseTool


# 业务 Tool 基类（agent: package-c-v1）
class BaseBusinessTool(BaseTool):
    """业务 Tool 抽象基类。

    复用 kivi_agent.core.tools.base.BaseTool 的协议（name / description / input_schema /
    category / invoke），不引入新字段。子类职责：
    - 提供具体 6 个 Tool 的 name / description / input_schema / category
    - 实现 invoke(params) 返回 ToolResult
    - 演示版必须 100% Mock，不发任何外部 HTTP 请求

    升级路径：当业务 Tool 需要从 RunContext 拿运行时参数（datasource_id / knowledge_base_id）
    时，新增 `async def invoke(self, params, *, ctx=None)` 重载；本基类保持
    向后兼容（ctx 可选）。
    """

    # 基类层声明 input_schema 类属性（v1 §4 契约：所有 BaseTool 子类必须有 input_schema）
    # 子类必须覆盖此属性；空 dict 表示"不暴露参数"（如未来的抽象基类扩展）
    input_schema: dict[str, Any] = {}
