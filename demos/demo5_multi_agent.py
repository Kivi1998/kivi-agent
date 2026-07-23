"""Demo 5：综合多能力任务（agent: package-demo-v7）。

# demo5_multi_agent.py（agent: package-demo-v7）
按 Wave 7 计划 §三 WT-K2 / demo5 设计：
- 输入：fixtures/demo5_multi_task_input.json（政策摘录 + 外部市场摘录 + 3 个子问题）
- 流程：rag + web_search + database + synthesizer 4 agent 协作（演示版用 4 个 Tool 模拟）
- 期望：报告 + ECharts chart metadata

演示版要点：
- 不真跑 4 agent（避免子 run 嵌套 + 真实 LLM 调用）
- 改用 4 个 Tool 串行调用 + 拼装结果，模拟 "4 agent 协作" 的语义
- 报告由 demo 自身合成（含 ECharts option dict 形式 chart metadata）

可独立运行：`uv run python -m demos.demo5_multi_agent`
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from kivi_agent.core.business.echarts_render import EchartsRenderTool
from kivi_agent.core.business.rag_query import RagQueryTool
from kivi_agent.core.business.web_search import WebSearchTool

from demos.base import DemoBase, DemoResult


# Demo 5：综合多能力任务（agent: package-demo-v7）
class Demo5MultiAgent(DemoBase):
    """综合多能力 Agent 演示：4 agent 协作产出报告 + 图表。"""

    name = "demo5_multi_agent"
    description = "综合多能力：rag + web_search + database + synthesizer 4 agent 协作 + 图表"

    # 跑 demo 业务逻辑（agent: package-demo-v7）
    async def run(self) -> DemoResult:
        # 1. 加载 fixture
        fixture = Path(__file__).parent / "fixtures" / "demo5_multi_task_input.json"
        fixture_data = json.loads(fixture.read_text(encoding="utf-8"))
        task: str = fixture_data["task"]
        policy_excerpt: str = fixture_data["policy_excerpt"]
        external_excerpt: str = fixture_data["external_excerpt"]
        questions: list[str] = fixture_data["questions"]

        # 2. rag agent：调 RagQueryTool 召回政策
        rag = RagQueryTool()
        rag_result = await rag.invoke(
            {"query": questions[0], "knowledge_base_id": "kb-policies"}
        )
        rag_payload = json.loads(rag_result.content) if not rag_result.is_error else {}

        # 3. web_search agent：调 WebSearchTool 拉外部信息
        #    WebSearchTool 直接返回 list[dict]（按 aigroup TavilyClient 对齐）
        ws = WebSearchTool()
        ws_result = await ws.invoke({"query": questions[1]})
        ws_results_list: list[dict[str, object]] = (
            json.loads(ws_result.content) if not ws_result.is_error else []
        )
        if not isinstance(ws_results_list, list):
            ws_results_list = []

        # 4. database agent：演示版不真起 database 工具（demo 3 已覆盖），
        #    这里手算数字作为"database agent 输出"（固定 4 行）
        db_rows = [
            {"region": "华东", "headcount": 320, "avg_salary_k": 28},
            {"region": "华南", "headcount": 180, "avg_salary_k": 25},
            {"region": "华北", "headcount": 240, "avg_salary_k": 30},
            {"region": "西南", "headcount": 120, "avg_salary_k": 22},
        ]

        # 5. synthesizer agent：合并 3 个子结果 + 调 echarts_render
        report_sections: list[dict[str, str]] = []
        report_sections.append(
            {
                "title": "1. 内部政策（来自 RAG）",
                "body": f"政策摘录：{policy_excerpt}",
                "source_id": ", ".join(
                    str(s.get("id", "")) for s in rag_payload.get("sources", [])
                ),
            }
        )
        report_sections.append(
            {
                "title": "2. 外部市场（来自 WebSearch）",
                "body": external_excerpt
                + " | 命中 URL: "
                + ", ".join(str(r.get("url", "")) for r in ws_results_list[:3]),
                "source_id": ", ".join(str(r.get("id", "")) for r in ws_results_list[:3]),
            }
        )
        report_sections.append(
            {
                "title": "3. 数据库聚合（来自 DatabaseAgent）",
                "body": (
                    f"按区域统计 headcount："
                    + ", ".join(
                        f"{r['region']}={r['headcount']}"  # type: ignore[arg-type]
                        for r in db_rows
                    )
                ),
                "source_id": "synthesizer-aggregated",
            }
        )
        report_sections.append(
            {
                "title": "4. 综合结论",
                "body": (
                    "结合内部年假政策 + 外部招聘市场 + 区域数据，"
                    "建议：在 headcount 增长较快的华东 / 华北区域适度提高年假弹性，"
                    "以保留核心人才。"
                ),
                "source_id": "synthesizer-final",
            }
        )

        # 6. echarts_render：按区域 headcount 出图
        echarts = EchartsRenderTool()
        chart_rows = [
            {"region": str(r["region"]), "headcount": int(r["headcount"])}  # type: ignore[arg-type]
            for r in db_rows
        ]
        chart_result = await echarts.invoke(
            {"rows": chart_rows, "chart_type": "bar"}
        )
        chart_payload = json.loads(chart_result.content) if not chart_result.is_error else {}

        # 7. 校验
        passed = (
            not rag_result.is_error
            and not ws_result.is_error
            and not chart_result.is_error
            and len(report_sections) == 4
            and len(chart_payload.get("option", {}).get("series", [])) > 0
        )

        artifacts = {
            "task": task,
            "rag_sources": rag_payload.get("sources", []),
            "web_results": ws_results_list,
            "db_rows": db_rows,
            "report_sections": report_sections,
            "chart_keys": list(chart_payload.get("option", {}).keys()),
            "chart_series_count": len(chart_payload.get("option", {}).get("series", [])),
        }
        summary = (
            f"rag_sources={len(artifacts['rag_sources'])} "
            f"web_results={len(ws_results_list)} "
            f"db_rows={len(db_rows)} "
            f"chart_series={artifacts['chart_series_count']}"
        )
        return DemoResult(
            name=self.name,
            status="passed" if passed else "failed",
            summary=summary,
            duration_seconds=0.0,
            artifacts=artifacts,
        )


# 入口：`uv run python -m demos.demo5_multi_agent`（agent: package-demo-v7）
def main() -> None:
    async def _go() -> DemoResult:
        async with Demo5MultiAgent() as demo:
            return await demo.execute()

    asyncio.run(_go())


if __name__ == "__main__":
    main()
