"""5 演示用例端到端测试（agent: package-demo-v7）。

# test_demos.py（agent: package-demo-v7）
按 Wave 7 计划 §三 WT-K2：
- 5 demo 各 1 case，全部用 FakeLlmProvider / Mock fetch（100% 离线）
- env guard: KIVI_RUN_DEMOS=1（CI 默认跳过）
- demo 5 加 1 case 端到端（验证报告 + chart metadata 结构）

跑法：
    KIVI_RUN_DEMOS=1 uv run pytest tests/integration/test_demos.py -q
"""
from __future__ import annotations

import asyncio
import os

import pytest
from demos.base import DemoBase, DemoResult, aggregate_reports
from demos.demo1_coding import Demo1Coding
from demos.demo2_rag import Demo2Rag
from demos.demo3_database import Demo3Database
from demos.demo4_frontend_map import Demo4FrontendMap
from demos.demo5_multi_agent import Demo5MultiAgent

# 5 demo 跑通需显式设置 KIVI_RUN_DEMOS=1（CI 默认 skip）
pytestmark = pytest.mark.skipif(
    os.environ.get("KIVI_RUN_DEMOS") != "1",
    reason="KIVI_RUN_DEMOS != 1; set KIVI_RUN_DEMOS=1 to run demos",
)


# 工具：异步跑一个 demo 类，返回 DemoResult
async def _run_demo(cls: type[DemoBase]) -> DemoResult:
    """异步跑一次 demo 类；返回 DemoResult。"""
    async with cls() as demo:
        return await demo.execute()


# 功能：demo1_coding 端到端——CodingAgent 修 add 函数 + pytest 通过 + 3 指标
# 设计：FakeLlmProvider 第 1 轮直接给出正确实现；最终 passed=2 / success=True
async def test_demo1_coding_passes() -> None:
    result = await _run_demo(Demo1Coding)
    assert result.status == "passed", f"demo1 failed: {result.summary}\n{result.error}"
    m = result.artifacts["metrics"]
    assert m["task_completion_rate"]["rate"] == 1.0
    assert result.artifacts["final_passed"] == 2


# 功能：demo2_rag 端到端——RagQueryTool 召回政策 + 含 source_id + ref_json
# 设计：Mock 模式无外部 HTTP；sources 列表至少 1 条；id 非空
async def test_demo2_rag_passes() -> None:
    result = await _run_demo(Demo2Rag)
    assert result.status == "passed", f"demo2 failed: {result.summary}\n{result.error}"
    assert result.artifacts["has_source_id"] is True
    assert result.artifacts["has_ref_json"] is True
    assert result.artifacts["source_count"] >= 1
    assert all(sid for sid in result.artifacts["source_ids"])


# 功能：demo3_database 端到端——SQLiteAdapter + query_database + echarts_render
# 设计：fixture 20 行 orders，Q1 总营收 = 44500（固定值）；echarts option 至少 1 series
async def test_demo3_database_passes() -> None:
    result = await _run_demo(Demo3Database)
    assert result.status == "passed", f"demo3 failed: {result.summary}\n{result.error}"
    assert result.artifacts["q1_revenue"] == 44500
    assert result.artifacts["row_count"] > 0
    assert "series" in result.artifacts["chart_keys"]


# 功能：demo4_frontend_map 端到端——3 GeoJSON URL 加载 + map.geojson_loaded 事件
# 设计：Mock fetch 循环返回 3 套 GeoJSON；演示版期望 3/3 ok + 3 事件
async def test_demo4_frontend_map_passes() -> None:
    result = await _run_demo(Demo4FrontendMap)
    assert result.status == "passed", f"demo4 failed: {result.summary}\n{result.error}"
    assert result.artifacts["url_count"] == 3
    assert result.artifacts["ok_count"] == 3
    assert result.artifacts["map_event_count"] == 3
    # 演示版 fake fetch：循环返回 3 套；每个含 features + bbox
    for load in result.artifacts["loads"]:
        assert load["ok"] is True
        assert load["loaded_features_count"] > 0
        assert load["bbox"] is not None


# 功能：demo5_multi_agent 端到端——4 agent 协作产出报告 + ECharts chart metadata
# 设计：4 tool 串行调用 + 4 section 报告 + 1 chart series
async def test_demo5_multi_agent_passes() -> None:
    result = await _run_demo(Demo5MultiAgent)
    assert result.status == "passed", f"demo5 failed: {result.summary}\n{result.error}"
    assert len(result.artifacts["report_sections"]) == 4
    assert result.artifacts["chart_series_count"] >= 1
    # 4 agent 各自的输出都非空
    assert len(result.artifacts["rag_sources"]) >= 1
    assert len(result.artifacts["web_results"]) >= 1
    assert len(result.artifacts["db_rows"]) >= 1


# 功能：5 demo 顺序跑通 + aggregate_reports 汇总正确
# 设计：端到端 smoke test：把 5 个 demo 结果聚合成 summary dict
async def test_all_5_demos_aggregate() -> None:
    results = []
    for cls in [Demo1Coding, Demo2Rag, Demo3Database, Demo4FrontendMap, Demo5MultiAgent]:
        r = await _run_demo(cls)
        results.append(r)
    summary = aggregate_reports(results)
    assert summary["total"] == 5
    assert summary["passed"] == 5
    assert summary["failed"] == 0
    assert summary["all_passed"] is True
    for entry in summary["results"]:
        assert entry["status"] == "passed", f"{entry['name']} failed: {entry['summary']}"


# 功能：DemoBase.execute 失败路径——run 抛异常时 status=failed
# 设计：构造一个故意 raise 的 demo；验证兜底逻辑
async def test_demo_base_handles_exception() -> None:
    class BoomDemo(DemoBase):
        name = "boom_demo"
        description = "故意抛异常的 demo（用于测兜底）"

        async def run(self) -> DemoResult:
            raise RuntimeError("boom")

    result = await _run_demo(BoomDemo)
    assert result.status == "failed"
    assert "boom" in (result.error or "")
    assert "RuntimeError" in (result.error or "")


# 同步驱动入口（agent: package-demo-v7）
def test_demos_sync_smoke() -> None:
    """sync 入口：跑 5 demo + 输出汇总。"""
    loop = asyncio.new_event_loop()
    try:
        results = []
        for cls in [Demo1Coding, Demo2Rag, Demo3Database, Demo4FrontendMap, Demo5MultiAgent]:
            results.append(loop.run_until_complete(_run_demo(cls)))
        summary = aggregate_reports(results)
        assert summary["all_passed"] is True
    finally:
        loop.close()
