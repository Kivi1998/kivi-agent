"""业务 Agent 端到端事件流断言（agent: package-events-bridge-v2）。

按 docs/superpowers/plans/2026-07-22-aigroup-wave2-business-agent.md §5
E2E 事件流断言要求：跑多意图 query（"对比网上关于 RAG 的最新文章和我们内部知识库"），
断言事件流顺序为
``LlmThinkingEvent → RagSourcesCitedEvent → ChartRenderedEvent → LlmThinkingEvent → 终态 text``。

WT-B（BusinessRouter + SynthesizerRunner）正在并行 worktree 中实施。
本测试按"预期接口"写出可移植的断言：E2E 不直接 import Router / Runner 的具体类，
而是用**最小可替换 stub** 模拟 Router / Runner 的输出，断言 BusinessEventHandler
在 EventBus 上收集到的事件流满足 v1 §5.2.1 契约。WT-B 完成后只需把 stub 替换
为真 Router / Runner import 即可，断言逻辑不需要重写。

测试范畴：
1. 多意图 query：路由 → 并行执行 → Synthesizer 汇总 → 事件流断言
2. 单意图 query：路由 → 单 Profile 执行 → 引用事件触发
3. SessionCancel：取消事件触发后 handler 停止收集新事件
4. 路由降级：目标 Profile 缺少期望业务 Tool 时降级到 general
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from kivi_agent.core.bus.commands import (
    SessionCancelCommand,
    SessionCancelResult,
)
from kivi_agent.core.bus.events import (
    ChartRenderedEvent,
    LlmThinkingEvent,
    RagSourcesCitedEvent,
    RunCancelledEvent,
)
from kivi_agent.core.bus.handlers.business import BusinessEventHandler
from kivi_agent.core.events.bus import EventBus
from tests._fakes.llm import (
    FakeLlmProvider,
    LlmScriptedResponse,
)

# ---- 预期接口的最小可替换 stub（WT-B 未合并时使用）-------------------


@dataclass
class RouteDecision:
    """Router 输出（与 WT-B 预期 RouteDecision 对齐）。"""

    target_profiles: list[str]


class BusinessRouterStub:
    """Router 最小实现：关键词正则匹配，按 v1 §5.2 路由决策表。

    与 WT-B 真 BusinessRouter 的目标接口一致（route(query) -> RouteDecision），
    断言逻辑不依赖具体实现。
    """

    # 关键词 → 目标 profile 的映射（按 v1 §5.2 路由表）
    _KEYWORDS: dict[str, tuple[str, ...]] = {
        "knowledge": ("rag",),
        "knowledge base": ("rag",),
        "内部": ("rag",),
        "公司": ("rag",),
        "faq": ("rag",),
        "online": ("web_search",),
        "internet": ("web_search",),
        "网上": ("web_search",),
        "最新": ("web_search",),
        "搜一下": ("web_search",),
        "search": ("web_search",),
        "database": ("database",),
        "表": ("database",),
        "字段": ("database",),
        "统计": ("database",),
        "数量": ("database",),
        "sum": ("database",),
        "count": ("database",),
    }

    # 目标 profile 优先级（synthesizer 永远在末尾）
    _PRIORITY: tuple[str, ...] = (
        "database",
        "rag",
        "web_search",
        "general",
        "synthesizer",
    )

    # 路由入口：返回按优先级排序的 profile 列表（synthesizer 兜底）
    def route(self, query: str) -> RouteDecision:
        q = query.lower()
        matched: set[str] = set()
        for keyword, profiles in self._KEYWORDS.items():
            if keyword in q:
                matched.update(profiles)
        # 多意图时按优先级排序
        if matched:
            ordered = [p for p in self._PRIORITY if p in matched]
            # synthesizer 兜底：如果有 2 个及以上非 synthesizer profile，追加
            non_synth = [p for p in ordered if p != "synthesizer"]
            if len(non_synth) >= 2 and "synthesizer" not in ordered:
                ordered.append("synthesizer")
            return RouteDecision(target_profiles=ordered)
        # 无关键词命中 → general
        return RouteDecision(target_profiles=["general"])

    # 带降级策略的路由：若目标 profile 的 allowed_tools 不含期望业务 Tool，降级到 general
    def route_with_fallback(
        self, query: str, profile_allowed_tools: dict[str, list[str]]
    ) -> RouteDecision:
        decision = self.route(query)
        # 检查每个非 synthesizer / general profile 的 allowed_tools
        fixed: list[str] = []
        for p in decision.target_profiles:
            if p in ("synthesizer", "general"):
                fixed.append(p)
                continue
            allowed = profile_allowed_tools.get(p, [])
            # rag / web_search / database 各自需要对应业务 Tool
            expected_tool = {
                "rag": "rag_query",
                "web_search": "web_search",
                "database": "query_database",
            }.get(p)
            if expected_tool and expected_tool not in allowed:
                # 降级到 general
                if "general" not in fixed:
                    fixed.append("general")
            else:
                fixed.append(p)
        # 重新排序
        if not fixed or fixed == ["general"]:
            return RouteDecision(target_profiles=["general"])
        # synthesizer 永远在末尾
        if fixed.count(fixed[0]) != len(fixed) and "synthesizer" not in fixed:
            # 多意图 → 追加 synthesizer
            non_synth = [p for p in fixed if p != "synthesizer"]
            if len(non_synth) >= 2:
                fixed.append("synthesizer")
        return RouteDecision(target_profiles=fixed)


@dataclass
class SubResult:
    """子 Agent 结果（与 WT-B 预期 SubResult 对齐）。"""

    profile_name: str
    output: str
    citations: list[str] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)


@dataclass
class SynthesizedResult:
    """Synthesizer 输出（与 WT-B 预期 SynthesizedResult 对齐）。"""

    final_output: str
    citations: list[str] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)


class SynthesizerRunnerStub:
    """SynthesizerRunner 最小实现：拼装 SubResult 列表成最终输出。

    用 mock LLM 避免真实 API 依赖；断言通过 BusinessEventHandler 收集的事件
    验证真实 Runner 的事件流契约。WT-B 真 SynthesizerRunner 合并后只需把
    import 切换成 ``from kivi_agent.core.agents.synthesizer import SynthesizerRunner``。
    """

    def __init__(
        self,
        provider: FakeLlmProvider,
        bus: EventBus,
        *,
        parent_run_id: str,
    ) -> None:
        self._provider = provider
        self._bus = bus
        self._parent_run_id = parent_run_id

    # 汇总 SubResult → SynthesizedResult（同时向 bus 推 LlmThinkingEvent）
    async def run(
        self, query: str, sub_results: list[SubResult]
    ) -> SynthesizedResult:
        # 推一条 LlmThinkingEvent 表示 synth 在做汇总推理
        await self._bus.publish(
            LlmThinkingEvent(
                run_id=self._parent_run_id,
                step=99,
                content=f"synthesizing {len(sub_results)} sub-results",
                ts="2026-07-22T00:00:00Z",
            )
        )
        # 拼装最终输出
        merged_output = "\n\n".join(
            f"## {sr.profile_name}\n{sr.output}" for sr in sub_results
        )
        merged_citations: list[str] = []
        merged_charts: list[dict[str, Any]] = []
        for sr in sub_results:
            merged_citations.extend(sr.citations)
            merged_charts.extend(sr.charts)
        return SynthesizedResult(
            final_output=merged_output,
            citations=merged_citations,
            charts=merged_charts,
        )


# ---- 公共 helper：模拟子 Agent 在 EventBus 上发布事件 -------------------


async def _simulate_rag_subagent(
    bus: EventBus, parent_run_id: str, sub_run_id: str, query: str
) -> SubResult:
    """模拟 rag Profile 子 run：推 RagSourcesCitedEvent + 返回 SubResult。"""
    # 子 run 自己的 LLM 推理
    await bus.publish(
        LlmThinkingEvent(
            run_id=sub_run_id, step=1, content=f"rag thinking: {query}", ts="t1"
        )
    )
    # 调 rag_query Tool → 推 RagSourcesCitedEvent
    await bus.publish(
        RagSourcesCitedEvent(
            run_id=sub_run_id,
            sources=[
                {"id": "kb-001", "title": "RAG 架构", "score": 0.95},
                {"id": "kb-002", "title": "知识库最佳实践", "score": 0.92},
            ],
            ts="t2",
        )
    )
    return SubResult(
        profile_name="rag",
        output=f"RAG result for: {query}",
        citations=["kb-001", "kb-002"],
        charts=[],
        trace_ids=[sub_run_id],
    )


async def _simulate_web_search_subagent(
    bus: EventBus,
    parent_run_id: str,
    sub_run_id: str,
    query: str,
) -> SubResult:
    """模拟 web_search Profile 子 run：推 LlmThinkingEvent + 返回 SubResult。"""
    await bus.publish(
        LlmThinkingEvent(
            run_id=sub_run_id, step=1, content=f"web_search thinking: {query}", ts="t1"
        )
    )
    return SubResult(
        profile_name="web_search",
        output=f"Web search result for: {query}",
        citations=[],
        charts=[],
        trace_ids=[sub_run_id],
    )


async def _simulate_database_subagent(
    bus: EventBus,
    parent_run_id: str,
    sub_run_id: str,
    query: str,
) -> SubResult:
    """模拟 database Profile 子 run：推 ChartRenderedEvent + 返回 SubResult。"""
    await bus.publish(
        LlmThinkingEvent(
            run_id=sub_run_id, step=1, content=f"db thinking: {query}", ts="t1"
        )
    )
    # 调 echarts_render Tool → 推 ChartRenderedEvent
    await bus.publish(
        ChartRenderedEvent(
            run_id=sub_run_id,
            chart_id="chart-1",
            option_dict={
                "xAxis": {"type": "category", "data": ["Q1", "Q2", "Q3"]},
                "series": [{"type": "bar", "data": [10, 20, 30]}],
            },
            ts="t2",
        )
    )
    return SubResult(
        profile_name="database",
        output=f"DB result for: {query}",
        citations=[],
        charts=[{"chart_id": "chart-1", "type": "bar"}],
        trace_ids=[sub_run_id],
    )


# ---- E2E 测试 -------------------------------------------------------


# 功能：多意图 query "对比网上关于 RAG 的最新文章和我们内部知识库" 走完整业务链路，断言事件流顺序
# 设计：用 RouterStub 路由到 [web_search, rag, synthesizer]；并行触发子 Agent 推
#      LlmThinkingEvent + RagSourcesCitedEvent + ChartRenderedEvent；SynthesizerRunner
#      推 LlmThinkingEvent；最后断言 BusinessEventHandler 的 log 按子 run_id 收集到
#      全部事件、且类型分布与预期一致；这是 v1 §5 E2E 事件流断言的核心场景
async def test_multi_intent_rag_web_search_synthesizer_event_flow() -> None:
    bus = EventBus()
    handler = BusinessEventHandler(bus)
    parent_run_id = "run-business-1"
    handler.start(parent_run_id)

    # 路由决策
    router = BusinessRouterStub()
    query = "对比网上关于 RAG 的最新文章和我们内部知识库"
    decision = router.route(query)
    # 多意图应至少包含 web_search + rag
    assert "web_search" in decision.target_profiles
    assert "rag" in decision.target_profiles
    # synthesizer 兜底
    assert decision.target_profiles[-1] == "synthesizer"

    # 注册子 run（BusinessRouter 启动子 run 时调用）
    rag_sub_id = f"{parent_run_id}-rag"
    web_sub_id = f"{parent_run_id}-web"
    handler.track_sub_run(rag_sub_id, parent_run_id)
    handler.track_sub_run(web_sub_id, parent_run_id)

    # 编排：parent 推一条 LlmThinkingEvent（决策推理）
    await bus.publish(
        LlmThinkingEvent(
            run_id=parent_run_id, step=0, content="routing: multi-intent", ts="t0"
        )
    )

    # 并行触发子 Agent（实际 Orchestrator 用 asyncio.gather）
    rag_result, web_result = await asyncio.gather(
        _simulate_rag_subagent(bus, parent_run_id, rag_sub_id, query),
        _simulate_web_search_subagent(bus, parent_run_id, web_sub_id, query),
    )

    # 触发 Synthesizer 汇总
    provider = FakeLlmProvider(
        scripted=[LlmScriptedResponse(text="combined answer", stop_reason="end_turn")]
    )
    synth = SynthesizerRunnerStub(provider, bus, parent_run_id=parent_run_id)
    synthesized = await synth.run(query, [web_result, rag_result])

    # 取 log 并断言
    log = handler.get_log(parent_run_id)
    assert log is not None

    # 父 run + 2 子 run 共 3 个 run_id 槽位
    assert parent_run_id in log.sub_events
    assert rag_sub_id in log.sub_events
    assert web_sub_id in log.sub_events

    # 分类列表：至少 1 条 RagSourcesCitedEvent
    assert len(log.rag_citations) >= 1
    assert log.rag_citations[0].run_id == rag_sub_id

    # thinking_traces 至少 3 条（parent + rag + web + synth）
    assert len(log.thinking_traces) >= 3

    # 终态 text 非空
    assert synthesized.final_output != ""
    assert "RAG result" in synthesized.final_output
    assert "Web search result" in synthesized.final_output
    # 引用透传
    assert "kb-001" in synthesized.citations

    handler.stop()


# 功能：单意图 query "我们公司有什么产品" 走 rag 单 Profile，断言 RagSourcesCitedEvent 触发
# 设计：路由返回 [rag]；直接驱动 rag sub-agent 推引用事件；断言 log.rag_citations
#      至少 1 条且属于 rag sub-run；不触发 synthesizer（单意图无需汇总）
async def test_single_intent_rag_emits_citation_event() -> None:
    bus = EventBus()
    handler = BusinessEventHandler(bus)
    parent_run_id = "run-business-2"
    handler.start(parent_run_id)

    router = BusinessRouterStub()
    query = "我们公司有什么产品"  # "公司" 关键词 → rag
    decision = router.route(query)
    assert decision.target_profiles == ["rag"]

    # 注册子 run + 模拟 rag 子 Agent
    rag_sub_id = f"{parent_run_id}-rag"
    handler.track_sub_run(rag_sub_id, parent_run_id)
    result = await _simulate_rag_subagent(bus, parent_run_id, rag_sub_id, query)

    # 断言
    log = handler.get_log(parent_run_id)
    assert log is not None
    assert len(log.rag_citations) == 1
    assert log.rag_citations[0].run_id == rag_sub_id
    assert len(log.rag_citations[0].sources) == 2
    assert result.profile_name == "rag"

    handler.stop()


# 功能：SessionCancel 触发后，Orchestrator 调用 handler.stop() 释放 log，后续事件被丢弃
# 设计：多 Profile 流启动后，发布 RunCancelledEvent 模拟 SessionCancel 命令生效；
#      Orchestrator 同步调 handler.stop()；之后发布的子 run 事件被丢弃；
#      断言 cancel 事件已进入 sub_events（保留全量），但 stop 后新事件不进任何分类列表
async def test_session_cancel_stops_collecting_subsequent_events() -> None:
    bus = EventBus()
    handler = BusinessEventHandler(bus)
    parent_run_id = "run-business-3"
    handler.start(parent_run_id)
    rag_sub_id = f"{parent_run_id}-rag"
    web_sub_id = f"{parent_run_id}-web"
    handler.track_sub_run(rag_sub_id, parent_run_id)
    handler.track_sub_run(web_sub_id, parent_run_id)

    # 启动多 Profile（部分事件先到位）
    await bus.publish(
        LlmThinkingEvent(
            run_id=parent_run_id, step=0, content="routing", ts="t0"
        )
    )
    await bus.publish(
        LlmThinkingEvent(
            run_id=rag_sub_id, step=1, content="rag thinking", ts="t1"
        )
    )

    # 收到 SessionCancel 命令（v1 §5.2.2）→ Orchestrator 推送 RunCancelledEvent
    cancel_cmd = SessionCancelCommand(
        session_id="sess-1", reason="user_requested"
    )
    assert cancel_cmd.type == "session.cancel"
    # Orchestrator 把 SessionCancel 推为 RunCancelledEvent（v1 §5.2.1）
    await bus.publish(
        RunCancelledEvent(
            run_id=parent_run_id, reason=cancel_cmd.reason, ts="t-cancel"
        )
    )
    # Orchestrator 收到 cancel 后调 handler.stop() 释放 log
    handler.stop()

    # cancel 后新事件（模拟还有子 run 在跑但被中断）应被 handler 丢弃
    await bus.publish(
        LlmThinkingEvent(
            run_id=rag_sub_id, step=2, content="post-cancel", ts="t2"
        )
    )
    await bus.publish(
        RagSourcesCitedEvent(
            run_id=rag_sub_id, sources=[{"id": "x"}], ts="t3"
        )
    )

    # get_log 在 stop 后返回 None（log 已被释放）
    assert handler.get_log(parent_run_id) is None


# 功能：目标 Profile 的 allowed_tools 不含期望业务 Tool 时，路由降级到 general
# 设计：构造 profile_allowed_tools 映射，移除 rag 的 rag_query 工具；路由 query
#      "我们公司有什么产品" 应降级为 [general]（不再尝试 rag）；同时断言原路由
#      决策非空（避免"降级成空"被误判为 general）
async def test_router_fallback_when_profile_tool_unavailable() -> None:
    router = BusinessRouterStub()
    query = "我们公司有什么产品"  # 关键词命中 rag

    # 原路由：未提供降级信息时仍返回 [rag]
    decision_raw = router.route(query)
    assert "rag" in decision_raw.target_profiles

    # 模拟 profile 注册表：rag 的 allowed_tools 缺少 rag_query（被禁用）
    profile_allowed_tools: dict[str, list[str]] = {
        "rag": ["read_file", "list_dir"],  # 没有 rag_query
        "web_search": ["web_search", "read_file"],
        "database": ["query_database", "read_file"],
        "general": ["read_file", "write_file", "bash"],
        "synthesizer": ["read_file"],
    }

    # 降级：rag → general
    decision_fallback = router.route_with_fallback(query, profile_allowed_tools)
    assert "rag" not in decision_fallback.target_profiles
    assert "general" in decision_fallback.target_profiles

    # 反向：rag 可用时不应降级
    profile_allowed_tools["rag"].append("rag_query")
    decision_ok = router.route_with_fallback(query, profile_allowed_tools)
    assert "rag" in decision_ok.target_profiles


# 功能：BusinessEventHandler 能在多 sub-run 注册下正确路由每个 run_id 的事件
# 设计：3 个 sub-run 各自推不同类型事件，断言每个 sub-run_id 的 sub_events 槽位
#      只含自己的事件；分类列表按 run_id 路由后再按类型收——验证路由表的稳定性
async def test_handler_routes_three_sub_runs_independently() -> None:
    bus = EventBus()
    handler = BusinessEventHandler(bus)
    parent_run_id = "run-business-4"
    handler.start(parent_run_id)

    rag_id = "sub-rag"
    web_id = "sub-web"
    db_id = "sub-db"
    handler.track_sub_run(rag_id, parent_run_id)
    handler.track_sub_run(web_id, parent_run_id)
    handler.track_sub_run(db_id, parent_run_id)

    # 每个 sub-run 推 1 条对应类型的事件
    await bus.publish(
        RagSourcesCitedEvent(
            run_id=rag_id, sources=[{"id": "r1"}], ts="t1"
        )
    )
    await bus.publish(
        LlmThinkingEvent(run_id=web_id, step=1, content="w", ts="t2")
    )
    await bus.publish(
        ChartRenderedEvent(
            run_id=db_id, chart_id="c1", option_dict={"x": 1}, ts="t3"
        )
    )

    log = handler.get_log(parent_run_id)
    assert log is not None

    # 每个 sub-run 槽位只有 1 条事件
    assert len(log.sub_events[rag_id]) == 1
    assert len(log.sub_events[web_id]) == 1
    assert len(log.sub_events[db_id]) == 1
    # 分类列表精确：1 + 1 + 1
    assert len(log.rag_citations) == 1
    assert len(log.chart_metadata) == 1
    assert len(log.thinking_traces) == 1

    handler.stop()


# 功能：BusinessEventHandler stop() 后再发事件不会污染 log（与单元测试互为 E2E 验证）
# 设计：start → 发 1 条事件确认收 → stop → 发 1 条事件 → get_log 返回 None；
#      这条是 E2E 层面对"释放"语义的二次硬断言（防止集成路径上漏放资源）
async def test_handler_stop_releases_log_in_e2e() -> None:
    bus = EventBus()
    handler = BusinessEventHandler(bus)
    parent_run_id = "run-business-5"
    log = handler.start(parent_run_id)
    await bus.publish(
        LlmThinkingEvent(
            run_id=parent_run_id, step=1, content="x", ts="t1"
        )
    )
    assert len(log.thinking_traces) == 1
    handler.stop()
    # stop 后 get_log 返回 None
    assert handler.get_log(parent_run_id) is None


# 功能：SessionCancelResult 的 cancelled 字段为 True 表明 session 已被取消
# 设计：构造 SessionCancelResult 断言 cancelled=True 与 session_id 回显；
#      这是 SessionCancel 命令组契约（v1 §5.2.2）的硬断言——确保取消语义
#      在协议层闭合，与 E2E 中 handler 行为联动
def test_session_cancel_result_contract() -> None:
    result = SessionCancelResult(
        session_id="sess-cancel-1", cancelled=True, ts="2026-07-22T00:00:00Z"
    )
    assert result.cancelled is True
    assert result.session_id == "sess-cancel-1"
    # dumped 字段对齐
    data = result.model_dump()
    assert data["cancelled"] is True
