"""6 业务 Tool 接入 ToolRegistry + Permission 测试（agent: package-c-v1）。

按任务书 T7 验证：
- _build_registry() 末尾注册了 6 个业务 Tool
- DEFAULT_POLICIES 含 6 条 ToolPolicy
- 6 Tool 都返回 mock 数据（端到端验证）
- 写入类 Tool（memory_save）默认 ASK；只读类（其余 5 个）默认 ALLOW
- 注释锚点 # <tool_name>（agent: package-c-v1）齐全（防止 merge 冲突定位）
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from kivi_agent.core.permissions.policy import DEFAULT_POLICIES, PermissionDecision


# v1 §1 冻结的 6 个业务 Tool 名称
SIX_BUSINESS_TOOLS: tuple[str, ...] = (
    "web_search",
    "rag_query",
    "query_database",
    "echarts_render",
    "memory_save",
    "memory_recall")


# 功能：DEFAULT_POLICIES 含全部 6 条 ToolPolicy
def test_default_policies_contain_all_six_business_tools() -> None:
    for tool_name in SIX_BUSINESS_TOOLS:
        assert tool_name in DEFAULT_POLICIES, f"Missing policy for {tool_name}"


# 功能：5 个只读业务 Tool 默认 ALLOW
@pytest.mark.parametrize(
    "tool_name", ["web_search", "rag_query", "query_database", "echarts_render", "memory_recall"]
)
def test_readonly_business_tools_default_allow(tool_name: str) -> None:
    policy = DEFAULT_POLICIES[tool_name]
    assert policy.default == PermissionDecision.ALLOW


# 功能：memory_save（写入类）默认 ASK
def test_memory_save_default_ask() -> None:
    assert DEFAULT_POLICIES["memory_save"].default == PermissionDecision.ASK


# 功能：注释锚点 # <tool_name>（agent: package-c-v1）齐全（按任务书硬性约束）
def test_comment_anchors_in_policy() -> None:
    policy_source = Path("src/kivi_agent/core/permissions/policy.py").read_text(encoding="utf-8")
    for tool_name in SIX_BUSINESS_TOOLS:
        anchor = f"# {tool_name}（agent: package-c-v1）"
        assert anchor in policy_source, f"Missing anchor {anchor!r} in policy.py"


# 功能：注释锚点在 runner.py 中齐全
def test_comment_anchors_in_runner() -> None:
    runner_source = Path("src/kivi_agent/core/runner.py").read_text(encoding="utf-8")
    for tool_name in SIX_BUSINESS_TOOLS:
        anchor = f"# {tool_name}（agent: package-c-v1）"
        assert anchor in runner_source, f"Missing anchor {anchor!r} in runner.py"


# 功能：_build_registry() 注册全部 6 个业务 Tool
def test_build_registry_registers_six_business_tools() -> None:
    from kivi_agent.core.config import KamaConfig
    from kivi_agent.core.runner import AgentRunner

    cfg = KamaConfig()
    runner = AgentRunner(cfg)
    task_manager = object()  # type: ignore[arg-type]  # 构造调用 _build_registry
    registry = runner._build_registry(task_manager)  # type: ignore[arg-type]
    # 6 个业务 Tool 都已注册
    for tool_name in SIX_BUSINESS_TOOLS:
        assert registry.get(tool_name) is not None, f"{tool_name} not registered"


# 功能：tool_schemas 暴露 6 个业务 Tool 给 LLM
def test_build_registry_tool_schemas_includes_business_tools() -> None:
    from kivi_agent.core.config import KamaConfig
    from kivi_agent.core.runner import AgentRunner

    cfg = KamaConfig()
    runner = AgentRunner(cfg)
    task_manager = object()  # type: ignore[arg-type]
    registry = runner._build_registry(task_manager)  # type: ignore[arg-type]
    schema_names = {s["name"] for s in registry.tool_schemas()}
    for tool_name in SIX_BUSINESS_TOOLS:
        assert tool_name in schema_names, f"{tool_name} not in tool_schemas"


# 功能：tool_whitelist 可选择性注册业务 Tool
def test_tool_whitelist_filters_business_tools() -> None:
    from kivi_agent.core.config import KamaConfig
    from kivi_agent.core.runner import AgentRunner

    cfg = KamaConfig()
    runner = AgentRunner(cfg)
    task_manager = object()  # type: ignore[arg-type]
    # 只允许 web_search
    registry = runner._build_registry(
        task_manager,  # type: ignore[arg-type]
        tool_whitelist=["web_search"],
    )
    assert registry.get("web_search") is not None
    # 其他 5 个不注册
    for tool_name in ["rag_query", "query_database", "echarts_render", "memory_save", "memory_recall"]:
        assert registry.get(tool_name) is None, f"{tool_name} should be filtered by whitelist"


# 功能：6 业务 Tool 端到端都能 invoke 返回 mock 数据（_build_registry 构造的工具实例可用）
@pytest.mark.parametrize("tool_name", SIX_BUSINESS_TOOLS)
async def test_business_tool_end_to_end_mock(tool_name: str) -> None:
    from kivi_agent.core.config import KamaConfig
    from kivi_agent.core.runner import AgentRunner

    cfg = KamaConfig()
    runner = AgentRunner(cfg)
    task_manager = object()  # type: ignore[arg-type]
    registry = runner._build_registry(task_manager)  # type: ignore[arg-type]
    tool = registry.get(tool_name)
    assert tool is not None
    # 构造各 Tool 的最小合法参数
    if tool_name == "web_search":
        params = {"query": "test"}
    elif tool_name == "rag_query":
        params = {"query": "test"}
    elif tool_name == "query_database":
        params = {"question": "test", "datasource_id": "ds-1"}
    elif tool_name == "echarts_render":
        params = {"rows": [{"x": "a", "y": 1}]}
    elif tool_name == "memory_save":
        # 用临时目录避免污染真实 ~/.kivi/memory/
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            from kivi_agent.core.business.memory_save import MemorySaveTool

            tmp_tool = MemorySaveTool(root=Path(tmpdir))
            result = await tmp_tool.invoke(params={"content": "test"})
            assert not result.is_error
            return
    elif tool_name == "memory_recall":
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            from kivi_agent.core.business.memory_recall import MemoryRecallTool

            tmp_tool = MemoryRecallTool(root=Path(tmpdir))
            result = await tmp_tool.invoke(params={"query": "test"})
            assert not result.is_error
            return
    else:
        pytest.fail(f"unknown tool: {tool_name}")
    result = await tool.invoke(params=params)
    assert not result.is_error, f"{tool_name} mock should not error: {result.content}"
    # 返回内容可解析为 JSON
    data = json.loads(result.content)
    assert isinstance(data, (dict, list))


# 功能：政策评估对各业务 Tool 返回正确决策
@pytest.mark.parametrize("tool_name", ["web_search", "rag_query", "query_database", "echarts_render", "memory_recall"])
def test_policy_evaluate_business_tools_allow(tool_name: str) -> None:
    from kivi_agent.core.permissions.policy import evaluate

    assert evaluate(tool_name, {}) == PermissionDecision.ALLOW


def test_policy_evaluate_memory_save_ask() -> None:
    from kivi_agent.core.permissions.policy import evaluate

    assert evaluate("memory_save", {}) == PermissionDecision.ASK
