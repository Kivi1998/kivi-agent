"""BusinessRouter 路由决策测试（Wave 2 B2）。

覆盖 Wave 2 plan §3.1 路由决策冻结表的 6 种场景 + Profile 不可用降级：
- 单意图：rag / web_search / database / general
- 多意图：多关键词命中按 ROUTE_PRIORITY 排序 + 末尾追加 synthesizer
- 降级：Profile 不存在或 allowed_tools 不满足期望业务 Tool → general
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from kivi_agent.core.agents.business_router import BusinessRouter, RouteDecision
from kivi_agent.core.agents.loader import AgentProfile

# ─────────────────────────── Mock ProfileLoader ───────────────────────────


@dataclass
class _MockProfileLoader:
    """测试用 ProfileLoader：内存表 + 加载时返回 AgentProfile。"""

    # name → AgentProfile 的映射；未注册时返回 None
    profiles: dict[str, AgentProfile] = field(default_factory=dict)
    # 记录调用次数：便于验证路由前确实查了 loader
    load_calls: list[str] = field(default_factory=list)

    def load(self, name: str) -> AgentProfile | None:
        self.load_calls.append(name)
        return self.profiles.get(name)


def _make_profile(name: str, allowed_tools: list[str]) -> AgentProfile:
    """构造一个最小可用 AgentProfile（只填 name + allowed_tools）。"""
    return AgentProfile(
        name=name,
        description=f"mock {name}",
        system_prompt=f"mock system prompt for {name}",
        allowed_tools=allowed_tools,
        model="mock-model",
    )


# 默认 5 个业务 Profile 都已注册，allowed_tools 与 plan §3 冻结表一致
@pytest.fixture
def mock_loader() -> _MockProfileLoader:
    return _MockProfileLoader(
        profiles={
            "general": _make_profile("general", ["read_file", "list_dir", "bash"]),
            "rag": _make_profile("rag", ["read_file", "rag_query"]),
            "web_search": _make_profile("web_search", ["read_file", "web_search"]),
            "database": _make_profile("database", ["read_file", "query_database", "echarts_render"]),
            "synthesizer": _make_profile("synthesizer", ["read_file", "list_dir"]),
        }
    )


@pytest.fixture
def router(mock_loader: _MockProfileLoader) -> BusinessRouter:
    return BusinessRouter(profile_loader=mock_loader)


# ─────────────────────────── 6 种路由场景（plan §3.1 冻结表） ───────────────────────────


# 功能：含 "我们公司" 关键词的 query 应路由到 [rag]（单意图，无 synthesizer）
# 设计：直接断言 target_profiles 精确匹配列表，避免误把 synthesizer 加进单意图路径
def test_route_rag_intent(router: BusinessRouter) -> None:
    decision = router.route("请介绍一下我们公司的产品线")
    assert isinstance(decision, RouteDecision)
    assert decision.intent == "rag"
    assert decision.target_profiles == ["rag"]
    assert decision.is_multi_intent is False
    assert "我们公司" in decision.matched_keywords


# 功能：含 "网上" / "搜一下" 关键词的 query 应路由到 [web_search]
# 设计：覆盖 2 个不同的关键词以验证 pattern 编译正确（不是仅匹配某一个）
@pytest.mark.parametrize("query", ["帮我搜一下最新的 AI 新闻", "查一下网上有什么开源项目"])
def test_route_web_search_intent(router: BusinessRouter, query: str) -> None:
    decision = router.route(query)
    assert decision.intent == "web_search"
    assert decision.target_profiles == ["web_search"]
    assert decision.is_multi_intent is False


# 功能：含 "表" / "统计" 关键词的 query 应路由到 [database]
# 设计：覆盖中文关键词 + 英文聚合函数（SUM/COUNT）2 个分支，确保大小写不敏感
@pytest.mark.parametrize(
    "query",
    [
        "统计一下订单表的数量",
        "查一下 sales 表的 SUM(amount)",
        "我们数据库有多少个字段？",
    ],
)
def test_route_database_intent(router: BusinessRouter, query: str) -> None:
    decision = router.route(query)
    assert decision.intent == "database"
    assert decision.target_profiles == ["database"]
    assert decision.is_multi_intent is False


# 功能：不含任何关键词的 query 应降级到 [general]（兜底）
# 设计：覆盖多种自然表达，确认 general 兜底不被误触（不被某一关键词模糊匹配）
@pytest.mark.parametrize(
    "query",
    ["你好", "今天天气不错", "帮我写一个 Python 函数", "解释一下什么是闭包"],
)
def test_route_general_fallback(router: BusinessRouter, query: str) -> None:
    decision = router.route(query)
    assert decision.intent == "general"
    assert decision.target_profiles == ["general"]
    assert decision.is_multi_intent is False
    assert decision.matched_keywords == []


# 功能：同时含 "我们公司" + "网上" 的 query 应路由到 [rag, web_search, synthesizer]
# 设计：验证 (1) ROUTE_PRIORITY 排序——rag 优先于 web_search（rag 在前）；
#      (2) 多意图时 synthesizer 必须追加在末尾作为汇总兜底
def test_route_multi_intent_priority(router: BusinessRouter) -> None:
    decision = router.route("对比一下我们公司文档和网上最新的资料")
    assert decision.is_multi_intent is True
    assert decision.intent == "rag"  # primary = 优先级最高的命中
    assert decision.target_profiles == ["rag", "web_search", "synthesizer"]


# 功能：多意图时 synthesizer 必须永远在末尾（兜底语义）
# 设计：parametrize 覆盖多种 intent 组合（2-3 个同时命中），每种都断言 synthesizer 在末位
@pytest.mark.parametrize(
    "query,expected_prefix",
    [
        # database 优先级 > rag：含 "我们公司" + "数据库" 时 database 排第一
        ("我们公司数据库的统计数据", ["database", "rag"]),
        # database 优先级 > web_search：含 "网上" + "数据库" 时 database 排第一
        ("网上搜一下数据库的统计方法", ["database", "web_search"]),
        # rag 优先级 > web_search：含 "知识库" + "网上" 时 rag 排第一
        ("对比知识库和网上新闻", ["rag", "web_search"]),
    ],
)
def test_route_synthesizer_always_last(
    router: BusinessRouter, query: str, expected_prefix: list[str]
) -> None:
    decision = router.route(query)
    assert decision.is_multi_intent is True
    # 末尾必须是 synthesizer
    assert decision.target_profiles[-1] == "synthesizer"
    # 前缀按 ROUTE_PRIORITY 排序
    assert decision.target_profiles[: len(expected_prefix)] == expected_prefix
    # 总长度 = 前缀长度 + 1 (synthesizer)
    assert len(decision.target_profiles) == len(expected_prefix) + 1


# ─────────────────────────── Profile 不可用降级 ───────────────────────────


# 功能：rag Profile 不在 loader 中（即 TOML 缺失）时应降级到 [general]
# 设计：模拟 WT-A 还没合入或某个 Profile 加载失败的情况；
#      路由决策必须 fail-safe，绝不能把 query 路由到一个不存在的 Profile；
#      intent 字段保留原始意图（"rag"）以便上层埋点，但 target_profiles 必须降级
def test_route_profile_not_loaded_falls_back_to_general() -> None:
    # 空 loader：所有 load() 都返回 None
    loader = _MockProfileLoader(profiles={})
    router = BusinessRouter(profile_loader=loader)

    decision = router.route("我们公司有什么新政策？")
    # 命中 rag 关键词 → 应该降级 general
    assert decision.target_profiles == ["general"]
    # intent 保留 primary（用于埋点/调试）
    assert decision.intent == "rag"
    # matched_keywords 记录实际命中的关键词
    assert "我们公司" in decision.matched_keywords


# 功能：rag Profile 的 allowed_tools 不含 rag_query 时应降级到 [general]
# 设计：模拟 rag TOML 错配 / Tool 未注册的情况；
#      即使关键词命中，没有 Tool 也无法完成子任务，必须降级
def test_route_profile_missing_required_tool_falls_back_to_general() -> None:
    # rag Profile 故意不绑定 rag_query
    loader = _MockProfileLoader(
        profiles={
            "rag": _make_profile("rag", ["read_file", "list_dir"]),  # 缺少 rag_query
            "web_search": _make_profile("web_search", ["web_search"]),
        }
    )
    router = BusinessRouter(profile_loader=loader)

    decision = router.route("我们公司的 FAQ 在哪里？")
    # 命中 rag 关键词但 rag 缺 Tool → 降级 general
    assert decision.target_profiles == ["general"]


# 功能：多意图降级时，所有缺 Tool 的 sub-Profile 都应被替换为 general，synthesizer 保持末尾
# 设计：模拟 rag + web_search 都没绑定 Tool 的边界情况；
#      验证降级时保留 synthesizer 兜底，避免合成链路也丢
def test_route_multi_intent_partial_downgrade() -> None:
    # rag 有 Tool，web_search 没有 Tool
    loader = _MockProfileLoader(
        profiles={
            "rag": _make_profile("rag", ["rag_query"]),
            "web_search": _make_profile("web_search", ["read_file"]),  # 缺 web_search
        }
    )
    router = BusinessRouter(profile_loader=loader)

    decision = router.route("对比我们公司和网上的资料")
    # rag 命中 + 有 Tool → 保留；web_search 命中但缺 Tool → 降级 general
    assert decision.target_profiles == ["rag", "general", "synthesizer"]


# ─────────────────────────── 元信息 / 数据类契约 ───────────────────────────


# 功能：RouteDecision 数据类的字段都应可访问且类型稳定
# 设计：构造一个完整决策，断言每个字段类型——这是后续埋点/事件载荷的依赖
def test_route_decision_field_types() -> None:
    d = RouteDecision(
        query="x", intent="rag", target_profiles=["rag"],
        is_multi_intent=False, confidence=0.8, matched_keywords=["我们公司"],
    )
    assert isinstance(d.query, str)
    assert isinstance(d.intent, str)
    assert isinstance(d.target_profiles, list)
    assert isinstance(d.is_multi_intent, bool)
    assert isinstance(d.confidence, float)
    assert isinstance(d.matched_keywords, list)
    # __str__ 至少应包含 intent / profiles
    s = str(d)
    assert "rag" in s


# 功能：BusinessRouter 暴露的关键静态常量（INTENT_KEYWORDS / ROUTE_PRIORITY）应符合 plan §3.1 冻结
# 设计：硬断言长度与具体意图名——这些是 v1 契约范围，变更需走 ADR
# Wave 7 扩展：加 frontend_tool 业务意图（demo 4 需要）
def test_router_class_constants_frozen() -> None:
    # 4 类业务意图 + 优先级（Wave 7 加 frontend_tool）
    assert set(BusinessRouter.INTENT_KEYWORDS.keys()) == {
        "rag",
        "web_search",
        "database",
        "frontend_tool",
    }
    assert BusinessRouter.ROUTE_PRIORITY == [
        "database",
        "rag",
        "web_search",
        "frontend_tool",
        "general",
    ]
    # 每个 intent 至少 1 个关键词
    for intent, kws in BusinessRouter.INTENT_KEYWORDS.items():
        assert len(kws) > 0, f"{intent} has no keywords"


# 功能：空 query 应降级 general，不抛异常
# 设计：边界条件——CLI/TUI 启动时可能传入空字符串，路由不能崩
@pytest.mark.parametrize("query", ["", "   ", "\n\t"])
def test_route_empty_query(router: BusinessRouter, query: str) -> None:
    decision = router.route(query)
    assert decision.intent == "general"
    assert decision.target_profiles == ["general"]
    assert decision.matched_keywords == []


# 功能：路由时确实查询了 ProfileLoader（防回归——空跑路径）
# 设计：单意图路径也会校验 allowed_tools，所以至少会调 1 次 loader.load()
def test_route_validates_via_loader(router: BusinessRouter, mock_loader: _MockProfileLoader) -> None:
    router.route("我们公司的产品")
    assert "rag" in mock_loader.load_calls


# 功能：未注入 profile_loader 时，BusinessRouter 应懒构造一个默认 loader
# 设计：保证上层可以无参使用 BusinessRouter()，但首次 route() 时会触发 loader 创建
def test_router_default_loader_lazy_init() -> None:
    router = BusinessRouter()
    # 第一次访问 profile_loader 属性才创建
    loader = router.profile_loader
    assert loader is not None
    # 不强制断言类型——只用类型提示标注为 AgentProfileLoader
