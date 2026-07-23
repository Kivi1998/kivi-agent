"""Demo 3：数据库 Agent（agent: package-demo-v7）。

# demo3_database.py（agent: package-demo-v7）
按 Wave 7 计划 §三 WT-K2 / demo3 设计：
- 输入：fixtures/demo3_orders.sql（20 行 orders 表）+ "Q1 总营收是多少"问题
- 流程：query_database Tool 用 SQLiteAdapter 跑真实 SQL（Wave 4 真实模式）
- 期望：返回数字 + 表格 + ECharts 元数据（金额 / 行数 / columns）

期望 Q1 总营收 = 8000+5000+3000+1500+9000+3500+2000+6000+4000+2500 = 44500

可独立运行：`uv run python -m demos.demo3_database`
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

from kivi_agent.core.business.echarts_render import EchartsRenderTool
from kivi_agent.core.business.query_database import QueryDatabaseTool
from kivi_agent.core.db.sqlite_adapter import SQLiteAdapter

from demos.base import DemoBase, DemoResult


# 从 SQL 文本里提取 CREATE TABLE / INSERT 语句（agent: package-demo-v7）
def _apply_sql_fixture(db_path: Path, sql_text: str) -> None:
    """把 fixture SQL 文本（CREATE + INSERT）应用到 sqlite db 文件。"""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(sql_text)
        conn.commit()
    finally:
        conn.close()


# Demo 3：数据库 Agent 用 QueryDatabaseTool + SQLiteAdapter 跑真实 SQL（agent: package-demo-v7）
class Demo3Database(DemoBase):
    """数据库 Agent 演示：用 SQLite + query_database 跑"Q1 总营收"。"""

    name = "demo3_database"
    description = "数据库 Agent：用 SQLite + query_database 算 Q1 总营收并出图表"

    # 跑 demo 业务逻辑（agent: package-demo-v7）
    async def run(self) -> DemoResult:
        # 1. 加载 SQL fixture + 写到 demo 自有 workdir
        sql_fixture = Path(__file__).parent / "fixtures" / "demo3_orders.sql"
        sql_text = sql_fixture.read_text(encoding="utf-8")
        db_path = self.workdir / "demo3.db"
        _apply_sql_fixture(db_path, sql_text)

        # 2. 调 query_database（真实模式：SQLiteAdapter）
        # 重置 counter（演示版用类属性，避免 demo 之间互相干扰）
        QueryDatabaseTool.reset_call_count()
        tool = QueryDatabaseTool(adapter=SQLiteAdapter(str(db_path)))
        question = "Q1 总营收是多少"
        result = await tool.invoke(
            {"question": question, "datasource_id": "ds-orders"}
        )

        if result.is_error:
            return DemoResult(
                name=self.name,
                status="failed",
                summary=f"query_database error: {result.content[:200]}",
                duration_seconds=0.0,
                artifacts={},
            )

        # 3. 解析结果
        payload = json.loads(result.content)
        rows: list[dict[str, object]] = payload.get("rows", [])
        columns: list[str] = payload.get("columns", [])

        # 4. 客户端手动算 Q1 总营收（2026-01/02/03）
        q1_revenue = 0
        for row in rows:
            month = str(row.get("month", ""))
            if month in ("2026-01", "2026-02", "2026-03"):
                q1_revenue += int(row.get("amount", 0) or 0)

        # 5. 调 echarts_render 生成图表元数据
        chart_tool = EchartsRenderTool()
        # 聚合：按月 + 区域
        by_month_region: dict[str, dict[str, int]] = {}
        for row in rows:
            if str(row.get("month", "")).startswith("2026-Q1"):
                continue
            month = str(row.get("month", ""))
            if not month.startswith("2026-0"):
                continue
            region = str(row.get("region", ""))
            amt = int(row.get("amount", 0) or 0)
            by_month_region.setdefault(month, {}).setdefault(region, 0)
            by_month_region[month][region] += amt
        # 转 echarts rows：[{month, 华东, 华南, 华北}, ...]
        chart_rows: list[dict[str, object]] = []
        for month in sorted(by_month_region.keys()):
            entry: dict[str, object] = {"month": month}
            for region, val in by_month_region[month].items():
                entry[region] = val
            chart_rows.append(entry)

        chart_result = await chart_tool.invoke(
            {"rows": chart_rows, "chart_type": "bar"}
        )
        chart_payload = json.loads(chart_result.content) if not chart_result.is_error else {}

        # 6. 校验：期望 Q1 总营收 = 44500
        expected = 44500
        ok = q1_revenue == expected and len(rows) > 0 and len(columns) > 0

        artifacts = {
            "question": question,
            "row_count": len(rows),
            "columns": columns,
            "q1_revenue": q1_revenue,
            "expected_q1_revenue": expected,
            "chart_id": chart_payload.get("option", {}).get("id", ""),
            "chart_keys": list(chart_payload.get("option", {}).keys()),
        }
        summary = (
            f"q1_revenue={q1_revenue} expected={expected} "
            f"rows={len(rows)} chart_keys={artifacts['chart_keys']}"
        )
        return DemoResult(
            name=self.name,
            status="passed" if ok else "failed",
            summary=summary,
            duration_seconds=0.0,
            artifacts=artifacts,
        )


# 入口：`uv run python -m demos.demo3_database`（agent: package-demo-v7）
def main() -> None:
    async def _go() -> DemoResult:
        async with Demo3Database() as demo:
            return await demo.execute()

    asyncio.run(_go())


if __name__ == "__main__":
    main()
