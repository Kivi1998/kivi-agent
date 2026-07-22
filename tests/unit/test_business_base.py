"""业务 Tool 基类 + 注册表测试（agent: package-c-v1）。

覆盖：
- BaseBusinessTool 能实例化（演示版需要子类至少实现 invoke 抽象方法）
- BaseBusinessTool 是 BaseTool 的子类（继承协议正确）
- BaseBusinessTool 的 input_schema 校验（Pydantic 风格）
- BusinessToolRegistry：register / get / list_names / unregister / clear
- 模块级单例 business_tool_registry 可独立使用
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from kivi_agent.core.business.base import BaseBusinessTool
from kivi_agent.core.business.registry import BusinessToolRegistry, business_tool_registry
from kivi_agent.core.tools.base import BaseTool


# 演示版最小业务 Tool：仅用于验证基类协议
class _SampleParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str


class _SampleBusinessTool(BaseBusinessTool):
    """演示版最小业务 Tool：返回固定 mock 文本。"""

    params_model = _SampleParams
    name = "sample_tool"
    category = "read"  # 只读
    description = "Sample business tool for base class testing."
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The query string.",
            },
        },
        "required": ["query"],
    }

    async def invoke(self, params: dict[str, object]) -> object:
        p = _SampleParams.model_validate(params)
        return f"mock: {p.query}"


# 功能：BaseBusinessTool 是 BaseTool 的子类（保证业务 Tool 接入 kivi-agent 体系无障碍）
def test_base_business_tool_is_base_tool_subclass() -> None:
    tool = _SampleBusinessTool()
    assert isinstance(tool, BaseTool)
    assert isinstance(tool, BaseBusinessTool)


# 功能：基类实例化后能拿到 name / description / category / input_schema
def test_base_business_tool_basic_attributes() -> None:
    tool = _SampleBusinessTool()
    assert tool.name == "sample_tool"
    assert tool.description == "Sample business tool for base class testing."
    assert tool.category == "read"
    assert isinstance(tool.input_schema, dict)
    assert tool.input_schema["type"] == "object"
    assert "query" in tool.input_schema["properties"]


# 功能：Pydantic 风格的 input_schema 校验——缺必填字段应该抛 ValidationError
def test_input_schema_validation_missing_required() -> None:
    tool = _SampleBusinessTool()
    with pytest.raises(ValidationError):
        _SampleParams.model_validate({})


# 功能：Pydantic 风格的 input_schema 校验——正常输入通过
def test_input_schema_validation_valid() -> None:
    tool = _SampleBusinessTool()
    p = _SampleParams.model_validate({"query": "hello"})
    assert p.query == "hello"


# 功能：BusinessToolRegistry.register / get 基本流程
def test_registry_register_and_get() -> None:
    reg = BusinessToolRegistry()
    tool = _SampleBusinessTool()
    reg.register(tool)
    assert reg.get("sample_tool") is tool
    assert reg.list_names() == ["sample_tool"]


# 功能：BusinessToolRegistry.get 不存在的 Tool 返回 None
def test_registry_get_missing_returns_none() -> None:
    reg = BusinessToolRegistry()
    assert reg.get("not_registered") is None


# 功能：BusinessToolRegistry.list_all 按名称排序返回实例列表
def test_registry_list_all_sorted() -> None:
    reg = BusinessToolRegistry()
    # 临时注册两个不同名 tool：通过 monkeypatch name 属性
    tool_a = _SampleBusinessTool()
    tool_b = _SampleBusinessTool()
    tool_b.name = "tool_b"
    reg.register(tool_a)
    reg.register(tool_b)
    names = [t.name for t in reg.list_all()]
    assert names == ["sample_tool", "tool_b"]


# 功能：BusinessToolRegistry.unregister 移除指定 Tool
def test_registry_unregister() -> None:
    reg = BusinessToolRegistry()
    tool = _SampleBusinessTool()
    reg.register(tool)
    reg.unregister("sample_tool")
    assert reg.get("sample_tool") is None
    assert reg.list_names() == []


# 功能：BusinessToolRegistry.clear 清空全部
def test_registry_clear() -> None:
    reg = BusinessToolRegistry()
    reg.register(_SampleBusinessTool())
    reg.clear()
    assert reg.list_names() == []


# 功能：BusinessToolRegistry 同名重复注册会覆盖（演示版简单策略）
def test_registry_register_overwrite() -> None:
    reg = BusinessToolRegistry()
    first = _SampleBusinessTool()
    second = _SampleBusinessTool()
    reg.register(first)
    reg.register(second)
    assert reg.get("sample_tool") is second
    assert reg.list_names() == ["sample_tool"]


# 功能：模块级单例 business_tool_registry 可直接使用（与构造的独立实例行为一致）
def test_module_level_singleton() -> None:
    assert isinstance(business_tool_registry, BusinessToolRegistry)
    # 独立实例与单例互不影响（list_names 反映各自状态）
    independent = BusinessToolRegistry()
    assert independent.list_names() == []
    # 单例初始状态应为空（演示版无内置 Tool）
    assert business_tool_registry.list_names() == []
