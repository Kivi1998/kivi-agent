"""5 演示用例脚本化（agent: package-demo-v7）。

# demos/__init__.py（agent: package-demo-v7）
按 docs/superpowers/plans/2026-07-23-aigroup-wave7-stage-8-closure.md §三 WT-K2：
- demo1_coding：编程 Agent（修 bug + 跑 pytest，Wave 6.1 T12）
- demo2_rag：知识库 Agent（问内部政策，Wave 4 RAG）
- demo3_database：数据库 Agent（自然语言问数，Wave 4 DB Adapter）
- demo4_frontend_map：前端操作 Agent（找 GeoJSON + 加载地图）
- demo5_multi_agent：综合多能力（政策 + 外部 + 图表 + 多 agent 协作）

通过 `python -m demos.demo1_coding` 单独跑；或 `scripts/run_demos.sh` 顺序跑 5 个。
"""
from __future__ import annotations

__all__ = [
    "base",
    "demo1_coding",
    "demo2_rag",
    "demo3_database",
    "demo4_frontend_map",
    "demo5_multi_agent",
]
