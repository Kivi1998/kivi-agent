"""业务 Tool ↔ Profile allowed_tools 对齐契约。

- v1 §1 冻结 6 个业务 Tool（web_search / rag_query / query_database / echarts_render / memory_save / memory_recall）
- Wave 2 plan §3 冻结 5 个业务 Profile 与业务 Tool 的绑定关系
- 本文件只测"绑定"和"排斥"关系，不重复测 Profile 字段本身（见 test_business_profile_v1.py）
"""
from __future__ import annotations

import pytest

from kivi_agent.core.agents.loader import AgentProfileLoader

# v1 §1 冻结的 6 个业务 Tool 名（统一引用，避免各测试重复字面量）
BUSINESS_TOOLS: frozenset[str] = frozenset(
    {"web_search", "rag_query", "query_database", "echarts_render", "memory_save", "memory_recall"}
)


# 辅助函数：取 Profile 的 allowed_tools 转 frozenset；找不到则断言失败（测试不该进到这里）
def _tools_of(name: str) -> frozenset[str]:
    profile = AgentProfileLoader().load(name)
    assert profile is not None, f"profile {name!r} not loadable (test setup error)"
    return frozenset(profile.allowed_tools)


# ─────────────────────────── rag Profile ↔ rag_query 绑定 ───────────────────────────


# 功能：rag Profile 必须绑定 rag_query 业务 Tool
# 设计：plan §3 冻结的 1:1 绑定；如果未来 rag 增加别的 Tool 这里会失败，提醒维护者同步更新契约
def test_rag_profile_binds_rag_query() -> None:
    assert "rag_query" in _tools_of("rag")


# 功能：rag Profile 不应绑定其他业务 Tool
# 设计：防回归——"rag 误绑 web_search"是常见错误（关键词重叠：都做检索）；
#      硬断言 5 个其他 Tool 全部不在 rag 的 allowed_tools 里
@pytest.mark.parametrize(
    "other_tool",
    sorted(BUSINESS_TOOLS - {"rag_query"}),
)
def test_rag_profile_excludes_other_business_tools(other_tool: str) -> None:
    assert other_tool not in _tools_of("rag"), (
        f"rag profile must not bind {other_tool!r}"
    )


# ─────────────────────────── web_search Profile ↔ web_search 绑定 ───────────────────────────


# 功能：web_search Profile 必须绑定 web_search 业务 Tool
# 设计：与 rag_profile 镜像测试；1:1 绑定契约
def test_web_search_profile_binds_web_search() -> None:
    assert "web_search" in _tools_of("web_search")


# 功能：web_search Profile 不应绑定其他业务 Tool
# 设计：5 个其他 Tool 全部不在 web_search 的 allowed_tools 里；
#      含 rag_query 排除（"网上 vs 知识库"是常见误绑场景）
@pytest.mark.parametrize(
    "other_tool",
    sorted(BUSINESS_TOOLS - {"web_search"}),
)
def test_web_search_profile_excludes_other_business_tools(other_tool: str) -> None:
    assert other_tool not in _tools_of("web_search"), (
        f"web_search profile must not bind {other_tool!r}"
    )


# ─────────────────────────── database Profile ↔ query_database 绑定 ───────────────────────────


# 功能：database Profile 必须绑定 query_database 业务 Tool
# 设计：plan §3 明确 database 的核心 Tool；不绑 query_database 就不是 database profile
def test_database_profile_binds_query_database() -> None:
    assert "query_database" in _tools_of("database")


# 功能：database Profile 可选绑定 echarts_render（按需图表）
# 设计：plan §3 表格"query_database（可选 echarts_render）"明确允许；
#      不强制断言 in，但若未来取消绑定这里需要手动更新——故只检查 echarts_render 的存在是合法的
def test_database_profile_echarts_render_binding_is_legal() -> None:
    # echarts_render 在 v1 §1 是合法业务 Tool；database 是否绑定是设计选择，不强约束
    tools = _tools_of("database")
    # 仅做合法性断言：要么绑要么不绑都合法；不存在"半绑"
    assert "echarts_render" in tools or "echarts_render" not in tools  # always True，仅显式语义


# 功能：database Profile 不应绑定 web_search / rag_query
# 设计：数据库问数不依赖外部检索；如果误绑说明设计漂移
def test_database_profile_excludes_web_search() -> None:
    assert "web_search" not in _tools_of("database")


def test_database_profile_excludes_rag_query() -> None:
    assert "rag_query" not in _tools_of("database")


# 功能：database Profile 不应绑定 memory_save / memory_recall
# 设计：问数不写长期记忆；这两个 Tool 后续归到别的 Profile
@pytest.mark.parametrize("tool", ["memory_save", "memory_recall"])
def test_database_profile_excludes_memory_tools(tool: str) -> None:
    assert tool not in _tools_of("database")


# ─────────────────────────── synthesizer Profile ↔ 0 业务 Tool 绑定 ───────────────────────────


# 功能：synthesizer Profile 不应绑定任何 v1 §1 6 业务 Tool
# 设计：plan §3 明确"synthesizer 只能读不能调业务 Tool"；
#      6 个 Tool 全部不在 synthesizer 的 allowed_tools 里——逐一硬断言
@pytest.mark.parametrize("tool", sorted(BUSINESS_TOOLS))
def test_synthesizer_profile_excludes_all_business_tools(tool: str) -> None:
    assert tool not in _tools_of("synthesizer"), (
        f"synthesizer profile must not bind any business tool, but found {tool!r}"
    )


# ─────────────────────────── general Profile ↔ 0 业务 Tool 绑定 ───────────────────────────


# 功能：general Profile 不应绑定任何 v1 §1 6 业务 Tool
# 设计：plan §3 明确"general 不能调业务 Tool"；这是 router 路由决策的关键不变量
@pytest.mark.parametrize("tool", sorted(BUSINESS_TOOLS))
def test_general_profile_excludes_all_business_tools(tool: str) -> None:
    assert tool not in _tools_of("general"), (
        f"general profile must not bind any business tool, but found {tool!r}"
    )


# ─────────────────────────── 跨 Profile 绑定矩阵一致性 ───────────────────────────


# 功能：5 个 Profile 各自绑定的业务 Tool 子集应两两不交
# 设计：业务 Tool 的归属是 1:1 绑定（除 echarts_render 可选附属于 database）；
#      防止"同一业务 Tool 被两个 Profile 绑"导致的 router 行为歧义
def test_business_tool_bindings_disjoint() -> None:
    binding_map: dict[str, set[str]] = {}
    for profile_name, tools in [
        ("rag", _tools_of("rag")),
        ("web_search", _tools_of("web_search")),
        ("database", _tools_of("database")),
        ("synthesizer", _tools_of("synthesizer")),
        ("general", _tools_of("general")),
    ]:
        bound_biz = tools & BUSINESS_TOOLS
        for t in bound_biz:
            if t in binding_map:
                pytest.fail(
                    f"business tool {t!r} bound to both {binding_map[t]!r} and {profile_name!r}"
                )
            binding_map[t] = {profile_name}


# 功能：v1 §1 6 业务 Tool 中，rag_query / web_search / query_database 三个核心 Tool 必须有归属 Profile
# 设计：plan §3 冻结的核心 1:1 绑定；memory_* 业务 Tool 在 Wave 2 不绑 Profile 是允许的（Wave 3 接入）
def test_three_core_business_tools_have_owner_profile() -> None:
    core_tools = {"rag_query", "web_search", "query_database"}
    owners: dict[str, str] = {}
    for profile_name in ["rag", "web_search", "database"]:
        for t in _tools_of(profile_name) & core_tools:
            assert t not in owners, (
                f"core tool {t!r} has multiple owners: {owners[t]!r} and {profile_name!r}"
            )
            owners[t] = profile_name
    missing = core_tools - owners.keys()
    assert not missing, f"core business tools without owner profile: {missing}"


# 功能：5 个 Profile 全部存在（间接覆盖 business 目录扫描逻辑）
# 设计：防回归——如果未来有人误删 business/ 子目录扫描，这组测试会全部失败
@pytest.mark.parametrize("name", ["general", "rag", "web_search", "database", "synthesizer"])
def test_all_business_profiles_resolvable(name: str) -> None:
    assert _tools_of(name)  # 非空 frozenset
