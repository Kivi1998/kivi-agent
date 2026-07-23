"""FakeAgentRuntime 单元测试（agent: package-web-e2e-v3）。

3 个场景：
1. 多意图 goal → 触发 rag.sources_cited + chart.rendered + run.finished
2. 取消 goal → 触发 run.cancelled 事件
3. Fallback goal → 触发 llm.thinking + run.finished

运行方式：``python3 -m pytest fixtures/test_fake_runtime.py -v``（从 tests/e2e_web/）
或 ``python3 -m pytest tests/e2e_web/fixtures/test_fake_runtime.py -v``（从 repo 根）
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# 让本目录可 import fake_runtime
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# repo 根 + src 也要能 import kivi_agent
_REPO_ROOT = _HERE.parent.parent.parent
_SRC = _REPO_ROOT / "src"
for p in (str(_REPO_ROOT), str(_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fake_runtime import FakeAgentRuntime  # noqa: E402

# ---- fixtures -----------------------------------------------------


@pytest.fixture
def runtime() -> FakeAgentRuntime:
    return FakeAgentRuntime()


async def _collect_events(runtime: FakeAgentRuntime, session_id: str) -> list[dict]:
    """收集 session 上推送的所有事件直到 run.finished 或超时。

    注：run.cancelled 不立即停止（cancel 模式后还会有 run.finished），
    只在收到 run.finished 时停止。
    """
    events: list[dict] = []
    try:
        async with asyncio.timeout(3.0):
            async for evt in runtime.subscribe_events(session_id):
                events.append(evt)
                if evt.get("type") == "run.finished":
                    return events
    except TimeoutError:
        pass
    return events


# ---- 测试 ----------------------------------------------------------


# 功能：多意图 goal "对比网上关于 RAG 的最新文章和我们内部知识库" 应触发 rag + chart + finished
# 设计：start_session → 收集所有事件 → 断言事件类型序列；这是 fake_runtime 的核心契约
async def test_multi_intent_emits_rag_chart_and_finished(runtime: FakeAgentRuntime) -> None:
    info = await runtime.start_session(
        user_id="u-1",
        goal="对比网上关于 RAG 的最新文章和我们内部知识库",
    )
    assert info.session_id
    assert info.run_id
    assert info.status == "active"

    events = await _collect_events(runtime, info.session_id)
    types = [e.get("type") for e in events]

    # 必须包含核心 4 类事件
    assert "rag.sources_cited" in types, f"missing rag.sources_cited in {types}"
    assert "chart.rendered" in types, f"missing chart.rendered in {types}"
    assert "run.started" in types
    assert "run.finished" in types, f"missing run.finished in {types}"

    # 事件顺序：run.started 在 rag/chart 之前
    started_idx = types.index("run.started")
    rag_idx = types.index("rag.sources_cited")
    chart_idx = types.index("chart.rendered")
    finished_idx = types.index("run.finished")
    assert started_idx < rag_idx
    assert started_idx < chart_idx
    assert max(rag_idx, chart_idx) < finished_idx

    # 所有事件带 session_id
    for e in events:
        assert e.get("session_id") == info.session_id

    # rag 事件带 sources
    rag_evt = next(e for e in events if e.get("type") == "rag.sources_cited")
    assert len(rag_evt["sources"]) >= 1

    # chart 事件带 option_dict
    chart_evt = next(e for e in events if e.get("type") == "chart.rendered")
    assert "option_dict" in chart_evt
    assert "series" in chart_evt["option_dict"]


# 功能：cancel goal "请取消" 走 cancel 模式，触发 run.cancelled 事件
# 设计：start_session(goal 含"取消") → cancel pattern 同步触发 run.cancelled + run.finished；
#      断言事件流含 run.cancelled，且 reason 正确
async def test_cancel_goal_emits_run_cancelled(runtime: FakeAgentRuntime) -> None:
    info = await runtime.start_session(
        user_id="u-1",
        goal="请取消这个任务",
    )
    events = await _collect_events(runtime, info.session_id)
    types = [e.get("type") for e in events]
    assert "run.cancelled" in types, f"missing run.cancelled in {types}"
    cancel_evt = next(e for e in events if e.get("type") == "run.cancelled")
    assert cancel_evt["reason"] == "user_requested"
    # cancel 模式也会推 run.finished（status=failed, reason=cancelled）
    finished_evt = next(e for e in events if e.get("type") == "run.finished")
    assert finished_evt["status"] == "failed"
    assert finished_evt["reason"] == "cancelled"


# 功能：fallback goal "你好" 不命中任何模式 → 走通用 llm.thinking + run.finished
# 设计：start_session 收集事件，断言只有 thinking + finished，无 rag/chart/cancelled
async def test_fallback_goal_emits_only_thinking_and_finished(
    runtime: FakeAgentRuntime,
) -> None:
    info = await runtime.start_session(user_id="u-1", goal="你好")
    events = await _collect_events(runtime, info.session_id)
    types = [e.get("type") for e in events]

    # 基础 lifecycle
    assert "session.created" in types
    assert "run.started" in types
    assert "run.finished" in types
    assert "llm.thinking" in types

    # 不应触发业务事件
    assert "rag.sources_cited" not in types
    assert "chart.rendered" not in types
    assert "run.cancelled" not in types

    # run.finished 状态是 success
    finished = next(e for e in events if e.get("type") == "run.finished")
    assert finished["status"] == "success"


# 功能：多订阅者独立 queue，互不干扰（验证 WebSocketBridge 兼容）
# 设计：同一 session 开 2 个订阅者，断言两个都收到完整事件流
async def test_multiple_subscribers_each_receive_all_events(
    runtime: FakeAgentRuntime,
) -> None:
    info = await runtime.start_session(
        user_id="u-1", goal="对比网上关于 RAG 的最新文章"
    )

    async def collect_one() -> list[dict]:
        return await _collect_events(runtime, info.session_id)

    # 并行收集
    a, b = await asyncio.gather(collect_one(), collect_one())
    assert len(a) >= 4
    assert len(b) >= 4
    # 两个订阅者收到的事件类型一致
    assert set(e["type"] for e in a) == set(e["type"] for e in b)
