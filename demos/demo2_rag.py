"""Demo 2：知识库 Agent（agent: package-demo-v7）。

# demo2_rag.py（agent: package-demo-v7）
按 Wave 7 计划 §三 WT-K2 / demo2 设计：
- 输入：fixtures/demo2_policies.txt（3 篇政策文档）+ "年假政策是什么"问题
- 流程：RagQueryTool（演示版 Mock）召回 + 格式化引用
- 期望：返回的 sources 列表含 source_id（按 Wave 4 RAG 演示版约定）

可独立运行：`uv run python -m demos.demo2_rag`
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from kivi_agent.core.business.rag_query import RagQueryTool

from demos.base import DemoBase, DemoResult


# 期望的 RAG 回答（演示版 Mock）—— 用于测试断言（agent: package-demo-v7）
# 真实模式下：调 RagKbClient 拿真实结果；演示版：返回固定 2 条 mock 引用
_EXPECTED_SOURCE_ID_KEYS = {"id", "title"}


# Demo 2：知识库 Agent 用 RagQueryTool 召回内部政策（agent: package-demo-v7）
class Demo2Rag(DemoBase):
    """知识库 Agent 演示：用 RagQueryTool 问内部政策并验证返回含 source_id。"""

    name = "demo2_rag"
    description = "知识库 Agent：用 RagQueryTool 召回内部年假政策 + 含 source_id"

    # 跑 demo 业务逻辑（agent: package-demo-v7）
    async def run(self) -> DemoResult:
        # 1. 加载 fixture（演示版不真用，仅展示有 3 篇政策文档）
        policy_file = Path(__file__).parent / "fixtures" / "demo2_policies.txt"
        policy_text = policy_file.read_text(encoding="utf-8")
        policy_doc_count = policy_text.count("=== 文档")

        # 2. 调 RagQueryTool（演示版 Mock，无外部 HTTP）
        tool = RagQueryTool()
        question = "年假政策是什么"
        result = await tool.invoke(
            {"query": question, "knowledge_base_id": "kb-policies"}
        )

        if result.is_error:
            return DemoResult(
                name=self.name,
                status="failed",
                summary=f"RagQueryTool returned error: {result.content[:200]}",
                duration_seconds=0.0,
                artifacts={"policy_doc_count": policy_doc_count},
            )

        # 3. 解析结果（按 C 报告 §3.6 aigroup 格式）
        payload = json.loads(result.content)
        sources: list[dict[str, object]] = payload.get("sources", [])
        answer: str = payload.get("answer", "")
        ref_json_str: str = payload.get("ref_json", "")

        # 4. 校验：sources 必须含 id（source_id）
        source_ids = [str(s.get("id", "")) for s in sources]
        has_source_id = all(bool(sid) for sid in source_ids)
        has_ref_json = "<ref_json>" in answer and ref_json_str != ""

        # 5. 汇总
        artifacts = {
            "policy_doc_count": policy_doc_count,
            "question": question,
            "source_count": len(sources),
            "source_ids": source_ids,
            "has_ref_json": has_ref_json,
            "answer_preview": answer[:200],
        }
        passed = has_source_id and has_ref_json and len(sources) >= 1
        summary = (
            f"policy_docs={policy_doc_count} sources={len(sources)} "
            f"has_source_id={has_source_id} has_ref_json={has_ref_json}"
        )
        return DemoResult(
            name=self.name,
            status="passed" if passed else "failed",
            summary=summary,
            duration_seconds=0.0,
            artifacts=artifacts,
        )


# 入口：`uv run python -m demos.demo2_rag`（agent: package-demo-v7）
def main() -> None:
    async def _go() -> DemoResult:
        async with Demo2Rag() as demo:
            return await demo.execute()

    asyncio.run(_go())


if __name__ == "__main__":
    main()
