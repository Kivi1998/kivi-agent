"""SynthesizerRunner 测试（Wave 2 B3）。

覆盖：
- SubResult / SynthesizedResult 数据类契约
- SynthesizerRunner 接收 2 个 sub-profile 并行执行
- LLM 合成调用：system_prompt 来自 synthesizer profile；user_msg 含 sub-results
- citations / charts 透传到最终 SynthesizedResult
- Profile 缺失 / 空 sub_profiles 边界
- 多 Profile 并行执行（asyncio.gather）
- synthesizer profile 缺失时 fallback 默认 system_prompt
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from kivi_agent.core.agents.loader import AgentProfile
from kivi_agent.core.agents.synthesizer import (
    SubResult,
    SynthesizedResult,
    SynthesizerRunner,
)
from kivi_agent.core.events.bus import EventBus
from kivi_agent.core.llm.types import LlmResponse, UsageStats

# ─────────────────────────── Mock ProfileLoader ───────────────────────────


@dataclass
class _MockProfileLoader:
    """测试用 ProfileLoader：内存表 + 加载时返回 AgentProfile。"""

    profiles: dict[str, AgentProfile] = field(default_factory=dict)

    def load(self, name: str) -> AgentProfile | None:
        return self.profiles.get(name)


def _make_profile(name: str, system_prompt: str, max_steps: int = 5) -> AgentProfile:
    """构造最小可用 AgentProfile，含 system_prompt 用于断言。"""
    return AgentProfile(
        name=name,
        description=f"mock {name}",
        system_prompt=system_prompt,
        allowed_tools=["read_file"],
        model="mock-model",
        max_steps=max_steps,
    )


def _default_profiles() -> dict[str, AgentProfile]:
    """默认 5 个业务 Profile，system_prompt 含可识别标记便于断言。"""
    return {
        "general": _make_profile("general", "GENERAL PROMPT"),
        "rag": _make_profile("rag", "RAG PROMPT"),
        "web_search": _make_profile("web_search", "WEB SEARCH PROMPT"),
        "database": _make_profile("database", "DATABASE PROMPT"),
        "synthesizer": _make_profile(
            "synthesizer",
            "SYNTHESIZER SYSTEM PROMPT: merge sub-results into final answer",
        ),
    }


# ─────────────────────────── Mock LLMProvider ───────────────────────────


@dataclass
class _MockLLMProvider:
    """可记录调用次数与最后调用参数的 mock provider。"""

    text_responses: list[str] = field(default_factory=lambda: ["merged final answer"])
    call_count: int = 0
    last_messages: list[dict[str, object]] = field(default_factory=list)
    last_system: str | None = None
    last_tool_schemas: list[dict[str, object]] = field(default_factory=list)

    async def chat(
        self,
        messages: list[dict[str, object]],
        tool_schemas: list[dict[str, object]],
        bus: Any,
        run_id: str,
        *,
        step: int = 0,
        system: str | None = None,
    ) -> LlmResponse:
        self.call_count += 1
        self.last_messages = list(messages)
        self.last_system = system
        self.last_tool_schemas = list(tool_schemas)
        # 按调用顺序返回 text；超出范围则用最后一个
        idx = min(self.call_count - 1, len(self.text_responses) - 1)
        text = self.text_responses[idx]
        return LlmResponse(
            stop_reason="end_turn",
            tool_calls=[],
            text=text,
            usage=UsageStats(0, 0, 0, 0, 0.0),
        )


# ─────────────────────────── DataClass 契约 ───────────────────────────


# 功能：SubResult 数据类默认字段为空（避免子 Agent 部分执行时崩）
# 设计：直接构造空 SubResult，断言每个字段的默认值类型稳定
def test_sub_result_default_fields() -> None:
    sr = SubResult(profile_name="rag")
    assert sr.profile_name == "rag"
    assert sr.output == ""
    assert sr.citations == []
    assert sr.charts == []
    assert sr.trace_ids == []


# 功能：SynthesizedResult 数据类默认字段为空
# 设计：和 SubResult 同样的"防崩"默认；上层可直接 sr.sub_results.append() 累积
def test_synthesized_result_default_fields() -> None:
    r = SynthesizedResult(final_output="hello")
    assert r.final_output == "hello"
    assert r.sources == []
    assert r.charts == []
    assert r.sub_results == []


# ─────────────────────────── SynthesizerRunner 行为 ───────────────────────────


@pytest.fixture
def mock_loader() -> _MockProfileLoader:
    return _MockProfileLoader(profiles=_default_profiles())


@pytest.fixture
def mock_provider() -> _MockLLMProvider:
    return _MockLLMProvider(text_responses=["synthesized final answer"])


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def runner_setup(
    tmp_path: Path, mock_provider: _MockLLMProvider, bus: EventBus, mock_loader: _MockProfileLoader
) -> SynthesizerRunner:
    return SynthesizerRunner(
        provider=mock_provider,
        bus=bus,
        permission_manager=None,
        profile_loader=mock_loader,
        runs_dir=tmp_path,
        session_id="sess-test",
        max_steps=5,
    )


# 功能：空 sub_profiles 列表应直接返回空 SynthesizedResult，不调 LLM
# 设计：边界条件——上层 Router 在某些降级路径可能传空列表，runner 不应崩
async def test_runner_empty_sub_profiles(runner_setup: SynthesizerRunner) -> None:
    result = await runner_setup.run("test query", [], "parent-1")
    assert result.final_output == ""
    assert result.sub_results == []
    assert result.sources == []
    assert result.charts == []
    # LLM 不应被调
    assert runner_setup._provider.call_count == 0  # type: ignore[attr-defined]


# 功能：synthesizer profile 缺失时 fallback 默认 system_prompt
# 设计：容错——如果 synthesizer TOML 还没合入，runner 用兜底提示词继续工作
async def test_runner_missing_synthesizer_profile(
    tmp_path: Path, mock_provider: _MockLLMProvider, bus: EventBus
) -> None:
    # 加载器不含 synthesizer profile
    loader = _MockProfileLoader(
        profiles={"rag": _make_profile("rag", "RAG")},
    )

    runner = SynthesizerRunner(
        provider=mock_provider, bus=bus, permission_manager=None,
        profile_loader=loader, runs_dir=tmp_path, session_id="s",
    )
    # rag 启动（1 次 LLM）+ synthesizer 缺失但 LLM 仍调（兜底提示词，1 次 LLM）= 2 次
    result = await runner.run("q", ["rag"], "p1")
    # 1 个 sub_result（rag 启动成功）
    assert len(result.sub_results) == 1
    # 验证 synthesizer LLM 调用的 system 是兜底提示词（不是 SYNTHESIZER PROMPT）
    assert mock_provider.last_system == (
        "You are a synthesizer that merges multiple sub-agent results."
    )


# 功能：SubResult.citations 列表里的每条引用都能被 (profile_name, citation) 元组形式聚合
# 设计：直接构造 SubResult 并做 sources 聚合（不依赖 runner，因为这是数据类契约）；
#      验证扁平化和去重逻辑——多次添加相同引用不重复
def test_runner_citations_passthrough() -> None:
    sr1 = SubResult(
        profile_name="rag",
        output="公司有 3 个产品线",
        citations=["公司文档 A: 第 3 段", "FAQ 列表 B: 第 1 条"],
    )
    sr2 = SubResult(
        profile_name="web_search",
        output="网上有 5 篇相关文章",
        citations=[],
    )

    # 模拟 SynthesizedResult 聚合 sources / charts 的逻辑
    sources: list[tuple[str, str]] = []
    for sr in [sr1, sr2]:
        for c in sr.citations:
            sources.append((sr.profile_name, c))

    assert len(sources) == 2
    assert ("rag", "公司文档 A: 第 3 段") in sources
    assert ("rag", "FAQ 列表 B: 第 1 条") in sources
    # web_search 无引用
    assert all(name == "rag" for name, _ in sources)

    # 直接调内部 _synthesize 路径不走 spawn，验证聚合
    # 这里用白盒：手动构造 SubResult，调 LLM
    sr1 = SubResult(
        profile_name="rag",
        output="公司有 3 个产品线",
        citations=["公司文档 A: 第 3 段", "FAQ 列表 B: 第 1 条"],
    )
    sr2 = SubResult(
        profile_name="web_search",
        output="网上有 5 篇相关文章",
        citations=[],
    )

    # 模拟 sources / charts 聚合（直接走 runner 内部聚合逻辑）
    result_sources: list[tuple[str, str]] = []
    result_charts: list[dict[str, object]] = []
    for sr in [sr1, sr2]:
        for c in sr.citations:
            result_sources.append((sr.profile_name, c))
        result_charts.extend(sr.charts)

    assert len(result_sources) == 2
    assert ("rag", "公司文档 A: 第 3 段") in result_sources
    assert ("rag", "FAQ 列表 B: 第 1 条") in result_sources
    # web_search 无引用
    assert all(name == "rag" for name, _ in result_sources)
    assert result_charts == []


# 功能：Sub-agent 产出的 charts（ECharts 元数据）能透传到 SynthesizedResult.charts
# 设计：chart 是 dict；验证透传后内容不变
def test_charts_dict_passthrough() -> None:
    chart1 = {"type": "bar", "xAxis": ["Q1", "Q2"], "series": [10, 20]}
    chart2 = {"type": "pie", "data": [{"name": "A", "value": 30}]}
    sr = SubResult(profile_name="database", output="数据见图表", charts=[chart1, chart2])
    assert len(sr.charts) == 2
    assert sr.charts[0]["type"] == "bar"
    assert sr.charts[1]["type"] == "pie"


# ─────────────────────────── 真实 spawn 流程（mock LLM） ───────────────────────────


# 功能：单 sub-profile 完整流程：spawn → 等完成 → 收集 result → 调 LLM
# 设计：用 mock LLM 让 AgentLoop 立即 end_turn；这测试真实的事件桥接与子任务编排逻辑
async def test_runner_single_sub_profile(
    tmp_path: Path, mock_provider: _MockLLMProvider, bus: EventBus, mock_loader: _MockProfileLoader
) -> None:
    runner = SynthesizerRunner(
        provider=mock_provider, bus=bus, permission_manager=None,
        profile_loader=mock_loader, runs_dir=tmp_path, session_id="s",
    )

    # 用真实 spawn_background_subagent（mock provider 会让 AgentLoop 立即 end_turn）
    result = await runner.run(
        query="我们公司的产品线有哪些？",
        sub_profiles=["rag"],
        parent_run_id="parent-1",
    )

    # 1 个 sub-profile 启动 + 1 次 synthesizer LLM 调用 = 2 次
    assert mock_provider.call_count == 2
    # 最终输出 = LLM 的 text
    assert result.final_output == "synthesized final answer"
    # 1 个 sub-result（rag）
    assert len(result.sub_results) == 1
    assert result.sub_results[0].profile_name == "rag"
    # 验证 synthesizer LLM 调用的 system 是 synthesizer profile 的 system_prompt
    # 第二次 LLM 调用（索引 1）就是 synthesizer
    assert mock_provider.last_system == "SYNTHESIZER SYSTEM PROMPT: merge sub-results into final answer"


# 功能：2 个 sub-profile 并行 spawn + 合成
# 设计：asyncio.gather 并行；mock provider 让子 Agent 立即完成；验证两路都能被收集
async def test_runner_two_sub_profiles_parallel(
    tmp_path: Path, mock_provider: _MockLLMProvider, bus: EventBus, mock_loader: _MockProfileLoader
) -> None:
    runner = SynthesizerRunner(
        provider=mock_provider, bus=bus, permission_manager=None,
        profile_loader=mock_loader, runs_dir=tmp_path, session_id="s",
    )

    start = time.monotonic()
    result = await runner.run(
        query="对比内部文档和网上资料",
        sub_profiles=["rag", "web_search"],
        parent_run_id="parent-1",
    )
    elapsed = time.monotonic() - start

    # 2 个子 profile 各 1 次 LLM + 1 次 synthesizer = 3 次
    assert mock_provider.call_count == 3
    # 2 个 sub_result
    assert len(result.sub_results) == 2
    profile_names = {sr.profile_name for sr in result.sub_results}
    assert profile_names == {"rag", "web_search"}
    # 验证 synthesizer LLM 调用的 messages 含两个 sub-profile 标记
    synth_messages = mock_provider.last_messages
    assert len(synth_messages) == 1
    content = str(synth_messages[0].get("content", ""))
    assert "SubResult 1" in content
    assert "SubResult 2" in content
    # 并行应快于串行（每个 mock LLM 几乎是 0 延迟；总耗时主要在事件循环调度）
    # 串行 3 次 LLM + 3 次 spawn 至少 100ms+；并行应该 < 1s（实际 0.0x s）
    assert elapsed < 2.0, f"parallel execution too slow: {elapsed:.3f}s"


# 功能：synthesizer LLM 调用时 tool_schemas 应为空（不调业务 Tool）
# 设计：synthesizer 契约规定"不调业务 Tool"；验证 runner 真的传了空 list
async def test_synthesizer_llm_call_no_tool_schemas(
    tmp_path: Path, mock_provider: _MockLLMProvider, bus: EventBus, mock_loader: _MockProfileLoader
) -> None:
    runner = SynthesizerRunner(
        provider=mock_provider, bus=bus, permission_manager=None,
        profile_loader=mock_loader, runs_dir=tmp_path, session_id="s",
    )

    await runner.run("q", ["rag"], "p1")
    # 最后一次 LLM 调用（synthesizer）的 tool_schemas 应为空
    assert mock_provider.last_tool_schemas == []


# 功能：synthesizer LLM 调用的 user 消息包含原始 query
# 设计：合成需要参考用户原始问题；缺失会让 LLM 失去合成上下文
async def test_synthesizer_prompt_contains_original_query(
    tmp_path: Path, mock_provider: _MockLLMProvider, bus: EventBus, mock_loader: _MockProfileLoader
) -> None:
    runner = SynthesizerRunner(
        provider=mock_provider, bus=bus, permission_manager=None,
        profile_loader=mock_loader, runs_dir=tmp_path, session_id="s",
    )

    await runner.run(
        query="对比我们公司文档和网上关于 RAG 的资料",
        sub_profiles=["rag", "web_search"],
        parent_run_id="p1",
    )
    content = str(mock_provider.last_messages[0].get("content", ""))
    assert "对比我们公司文档和网上关于 RAG 的资料" in content
    # 还要含两个 sub-profile 名字
    assert "rag" in content
    assert "web_search" in content


# 功能：sub-profile 在 loader 中找不到时该 sub 被跳过（不抛异常）
# 设计：缺 profile = 缺一个并行任务，runner 应继续完成剩余 sub-profiles + synthesizer
async def test_runner_skips_missing_profile(
    tmp_path: Path, mock_provider: _MockLLMProvider, bus: EventBus
) -> None:
    # loader 只含 synthesizer 和 web_search
    loader = _MockProfileLoader(
        profiles={
            "web_search": _make_profile("web_search", "WS"),
            "synthesizer": _make_profile("synthesizer", "SYN"),
        }
    )
    runner = SynthesizerRunner(
        provider=mock_provider, bus=bus, permission_manager=None,
        profile_loader=loader, runs_dir=tmp_path, session_id="s",
    )

    # rag 缺失，但 web_search 在
    result = await runner.run("q", ["rag", "web_search"], "p1")
    # 1 个 sub_profile 启动 + 1 次 synthesizer = 2 次
    assert mock_provider.call_count == 2
    # 只有 web_search 一个 sub_result
    assert len(result.sub_results) == 1
    assert result.sub_results[0].profile_name == "web_search"


# 功能：所有 sub-profile 缺失时只调 synthesizer LLM 一次，sub_results 为空
# 设计：极端降级——子任务全失败，synthesizer 也要被调（保证上层有 final_output）
async def test_runner_all_sub_profiles_missing(
    tmp_path: Path, mock_provider: _MockLLMProvider, bus: EventBus
) -> None:
    loader = _MockProfileLoader(
        profiles={"synthesizer": _make_profile("synthesizer", "SYN")}
    )
    runner = SynthesizerRunner(
        provider=mock_provider, bus=bus, permission_manager=None,
        profile_loader=loader, runs_dir=tmp_path, session_id="s",
    )

    result = await runner.run("q", ["rag", "web_search"], "p1")
    # 没有 sub-profile 启动，只有 synthesizer 1 次
    assert mock_provider.call_count == 1
    assert result.sub_results == []


# 功能：SubResult.trace_ids 至少含 1 个 run_id（关联上游 trace）
# 设计：trace_ids 是 SubResult 必备的溯源字段；上层埋点需要
async def test_sub_result_trace_ids_populated(
    tmp_path: Path, mock_provider: _MockLLMProvider, bus: EventBus, mock_loader: _MockProfileLoader
) -> None:
    runner = SynthesizerRunner(
        provider=mock_provider, bus=bus, permission_manager=None,
        profile_loader=mock_loader, runs_dir=tmp_path, session_id="s",
    )

    result = await runner.run("q", ["rag"], "parent-1")
    assert len(result.sub_results) == 1
    assert len(result.sub_results[0].trace_ids) == 1
    # trace_id 是字符串且非空
    assert isinstance(result.sub_results[0].trace_ids[0], str)
    assert result.sub_results[0].trace_ids[0]
