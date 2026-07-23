"""业务意图路由决策器（Wave 2 B2）。

根据用户 query 匹配关键词并返回按优先级排序的 Profile 名列表。轻量级实现：
- 关键词正则匹配 + 优先级 fallback
- 多意图场景：返回多个 sub-Profile + 末尾追加 synthesizer 兜底
- 单一意图场景：只返回 1 个 Profile（不含 synthesizer）
- 路由前校验目标 Profile 的 allowed_tools 是否包含期望的业务 Tool；缺失则降级 general

升级路径：未来用 LLM-based intent classification（v2，不在 Wave 2 范围）。
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import ClassVar, Literal, cast

from kivi_agent.core.agents.loader import AgentProfile, AgentProfileLoader

# 业务 Profile 意图类型；synthesizer 仅作为多意图汇总兜底
BusinessIntent = Literal["rag", "web_search", "database", "frontend_tool", "general", "synthesizer"]

# 各意图对应的"必须存在的"业务 Tool（路由降级校验用）
# 任何 Profile 若要承接该意图，allowed_tools 必须包含此集合
_INTENT_REQUIRED_TOOLS: dict[str, frozenset[str]] = {
    "rag": frozenset({"rag_query"}),
    "web_search": frozenset({"web_search"}),
    "database": frozenset({"query_database"}),
    "frontend_tool": frozenset({"web_search", "map_load"}),  # demo4 用
    "general": frozenset(),  # general 只需基础工具，不强制业务 Tool
    "synthesizer": frozenset(),  # synthesizer 只需基础工具，不强制业务 Tool
}


# 路由决策结果（含中间元信息，便于上层做埋点/调试）
@dataclass
class RouteDecision:
    """路由决策结果。"""

    query: str
    intent: BusinessIntent
    target_profiles: list[str] = field(default_factory=list)
    is_multi_intent: bool = False
    confidence: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)

    # 渲染为简短摘要；用于日志/事件载荷
    def __str__(self) -> str:
        profiles = ", ".join(self.target_profiles) if self.target_profiles else "(empty)"
        return (
            f"RouteDecision(intent={self.intent}, profiles=[{profiles}], "
            f"multi={self.is_multi_intent}, conf={self.confidence:.2f})"
        )


# 业务意图分类 + 路由决策器（轻量级关键词版）
class BusinessRouter:
    """业务意图分类 + 路由决策器。"""

    # 关键词正则表（冻结于 Wave 2 plan §3.1）
    INTENT_KEYWORDS: ClassVar[dict[str, list[str]]] = {
        "rag": ["我们公司", "内部文档", "FAQ", "知识库", "内部资料"],
        "web_search": ["网上", "最新", "搜一下", "搜一搜", "互联网", "新闻"],
        "database": ["表", "字段", "统计", "数量", "SUM", "COUNT", "AVG", "数据库", "问数"],
        "frontend_tool": ["地图", "加载", "前端", "渲染", "GeoJSON", "map"],
    }

    # 路由优先级：database > rag > web_search > frontend_tool > general（多意图时按此排序）
    ROUTE_PRIORITY: ClassVar[list[str]] = [
        "database",
        "rag",
        "web_search",
        "frontend_tool",
        "general",
    ]

    # 单 Profile → 期望业务 Tool（与 _INTENT_REQUIRED_TOOLS 保持一致；外部可见）
    INTENT_TOOL_REQUIREMENTS: ClassVar[dict[str, frozenset[str]]] = _INTENT_REQUIRED_TOOLS

    # 构造 BusinessRouter；profile_loader=None 时按需懒构造一个（便于测试时注入 mock）
    def __init__(self, profile_loader: AgentProfileLoader | None = None) -> None:
        self._profile_loader = profile_loader

    # 返回当前使用的 ProfileLoader（懒构造）
    def _loader(self) -> AgentProfileLoader:
        if self._profile_loader is None:
            self._profile_loader = AgentProfileLoader()
        return self._profile_loader

    # 对外暴露 loader；测试和上层需要校验 allowed_tools 时可直接拿
    @property
    def profile_loader(self) -> AgentProfileLoader:
        return self._loader()

    # 路由决策主入口：返回 RouteDecision
    def route(self, query: str) -> RouteDecision:
        """对 query 做关键词匹配，输出路由决策。"""
        if not query or not query.strip():
            # 空 query 一律降级 general（避免崩溃）
            return RouteDecision(
                query=query,
                intent="general",
                target_profiles=["general"],
                is_multi_intent=False,
                confidence=0.0,
                matched_keywords=[],
            )

        matched = self._match_intent(query)
        if not matched:
            return RouteDecision(
                query=query,
                intent="general",
                target_profiles=["general"],
                is_multi_intent=False,
                confidence=0.0,
                matched_keywords=[],
            )

        is_multi = self._is_multi_intent(matched)
        if is_multi:
            # 多意图：按 ROUTE_PRIORITY 排序 + 末尾追加 synthesizer 兜底
            ordered_intents: list[str] = [i for i in self.ROUTE_PRIORITY if i in matched]
            target_profiles: list[str] = list(ordered_intents) + ["synthesizer"]
            primary: BusinessIntent = cast(BusinessIntent, ordered_intents[0])
        else:
            # 单意图：唯一意图对应的 Profile
            primary = cast(BusinessIntent, next(iter(matched)))
            target_profiles = [primary]

        # 校验目标 Profile 的 allowed_tools；若不满足期望 Tool，降级 general
        target_profiles, downgraded = self._validate_tool_availability(target_profiles)

        # 计算置信度：单意图默认 0.7；多意图按命中数提升；降级时折扣
        if is_multi:
            confidence = min(1.0, 0.6 + 0.1 * len(matched))
        else:
            confidence = 0.7
        if downgraded:
            confidence = min(confidence, 0.5)

        # 扁平化 matched（dict[intent, list[kw]]）为扁平去重关键词列表
        flat_kws: list[str] = []
        for kws in matched.values():
            flat_kws.extend(kws)

        return RouteDecision(
            query=query,
            intent=primary,
            target_profiles=target_profiles,
            is_multi_intent=is_multi,
            confidence=round(confidence, 3),
            matched_keywords=sorted(set(flat_kws)),
        )

    # 关键词匹配：返回 {intent: [matched_keywords]} 字典
    def _match_intent(self, query: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for intent, kws in self.INTENT_KEYWORDS.items():
            hits: list[str] = []
            for kw in kws:
                if kw in query:
                    hits.append(kw)
            if hits:
                result[intent] = hits
        return result

    # 判断是否多意图（命中 ≥ 2 个不同 intent）
    def _is_multi_intent(self, matched: dict[str, list[str]]) -> bool:
        return len(matched) >= 2

    # 校验每个目标 Profile 的 allowed_tools 是否满足意图所需的业务 Tool；
    # 不满足则把该 Profile 替换为 general（保留 synthesizer 兜底）
    def _validate_tool_availability(
        self, target_profiles: Sequence[str]
    ) -> tuple[list[str], bool]:
        """校验目标 Profile 的 allowed_tools；不满足期望 Tool 时降级 general。

        返回 (调整后的 profiles, 是否发生降级)。
        """
        if not target_profiles:
            return list(target_profiles), False

        loader = self._loader()
        adjusted: list[str] = []
        downgraded = False

        for name in target_profiles:
            required = _INTENT_REQUIRED_TOOLS.get(name, frozenset())
            # synthesizer / general 无业务 Tool 强制要求，跳过校验
            if not required:
                adjusted.append(name)
                continue

            profile = loader.load(name)
            if profile is None:
                # 加载不到：保守起见降级 general（避免路由到不存在的 Profile）
                adjusted.append("general")
                downgraded = True
                continue

            if not self._profile_satisfies(profile, required):
                # allowed_tools 不满足期望业务 Tool：降级 general
                adjusted.append("general")
                downgraded = True
            else:
                adjusted.append(name)

        return adjusted, downgraded

    # 检查 Profile.allowed_tools 是否覆盖 required 集合
    @staticmethod
    def _profile_satisfies(profile: AgentProfile, required: frozenset[str]) -> bool:
        allowed = set(profile.allowed_tools)
        return required.issubset(allowed)
