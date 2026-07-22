"""6 个 v1 §1 业务 Tool 的 Mock 数据 fixture。

与 C 阶段的 mock 业务 Tool（`kivi_agent.core.business` 下的替身类）配合使用：
- 本文件只提供**数据**（输入/输出 fixture）
- C 阶段提供**行为**（实际 invoke 逻辑的替身）

为何要分开：
- 数据 fixture 稳定（与契约 v1 绑定），可跨 C 阶段多次复用
- 行为替身由 C 阶段自己实现（知道业务 Tool 的副作用）
- 单元测试只需要"标准输入 → 标准输出"对，不需要真 Tool 的复杂逻辑

使用方式：
    from tests._fakes import make_fixtures

    fixtures = make_fixtures()
    web_search_in = fixtures.web_search.input(query="kivi-agent")
    web_search_out = fixtures.web_search.output(query="kivi-agent", top_k=3)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class WebSearchFixture:
    """v1 §1 `web_search` 业务 Tool 的 mock 数据。"""

    name: str = "web_search"
    # 输入：Tavily 风格 query + top_k
    # 输出：result 列表，每条 {title, url, content, score}
    sample_query: str = "kivi-agent v1 contract"
    sample_top_k: int = 3
    sample_results: list[dict[str, str]] = field(
        default_factory=lambda: [
            {
                "title": "Kivi Agent 文档",
                "url": "https://docs.kivi.example/agent",
                "content": "kivi-agent 是本地 AI Agent 框架...",
                "score": "0.95",
            },
            {
                "title": "Wave 1 任务书",
                "url": "https://docs.kivi.example/wave1",
                "content": "5 个 Agent 并行实施 v1 契约...",
                "score": "0.88",
            },
        ]
    )

    # 构造示例 input dict
    def input(self, query: str | None = None, top_k: int | None = None) -> dict[str, Any]:
        return {
            "query": query if query is not None else self.sample_query,
            "top_k": top_k if top_k is not None else self.sample_top_k,
        }

    # 构造示例 output dict
    def output(self, query: str | None = None, top_k: int | None = None) -> dict[str, Any]:
        return {
            "query": query if query is not None else self.sample_query,
            "results": list(self.sample_results),
        }


@dataclass(frozen=True)
class RagQueryFixture:
    """v1 §1 `rag_query` 业务 Tool 的 mock 数据。

    注意：v1 冻结 `rag_query`（含内部 rewrite + retrieval），
    所以 fixture 一次同时给 `rewritten_query` 和 `retrieved_chunks`。
    """

    name: str = "rag_query"
    sample_question: str = "kivi-agent 的 schema_version 是几？"
    sample_kb_id: str = "kb-wiki"
    sample_chunks: list[dict[str, str]] = field(
        default_factory=lambda: [
            {
                "doc_id": "v1-contract#para-2",
                "content": "schema_version = 1 是当前冻结版本",
                "score": "0.92",
            },
            {
                "doc_id": "v1-contract#para-58",
                "content": "RunContext.schema_version 默认 1",
                "score": "0.81",
            },
        ]
    )

    def input(self, question: str | None = None, kb_id: str | None = None) -> dict[str, Any]:
        return {
            "question": question if question is not None else self.sample_question,
            "knowledge_base_id": kb_id if kb_id is not None else self.sample_kb_id,
            "top_k": 5,
        }

    def output(self, question: str | None = None) -> dict[str, Any]:
        return {
            "rewritten_query": f"(重写) {question or self.sample_question}",
            "chunks": list(self.sample_chunks),
            "citations": [c["doc_id"] for c in self.sample_chunks],
        }


@dataclass(frozen=True)
class QueryDatabaseFixture:
    """v1 §1 `query_database` 业务 Tool 的 mock 数据。

    两阶段：先 SELECT 验证，再出实际查询。
    """

    name: str = "query_database"
    sample_datasource_id: str = "ds-prod"
    sample_question: str = "近 7 天活跃用户数"
    sample_columns: list[str] = field(
        default_factory=lambda: ["day", "active_users"]
    )
    sample_rows: list[list[Any]] = field(
        default_factory=lambda: [
            ["2026-07-15", 1234],
            ["2026-07-16", 1302],
            ["2026-07-17", 1187],
        ]
    )

    def input(self, question: str | None = None) -> dict[str, Any]:
        return {
            "question": question if question is not None else self.sample_question,
            "datasource_id": self.sample_datasource_id,
        }

    def output(self) -> dict[str, Any]:
        return {
            "sql": "SELECT day, active_users FROM metrics WHERE day >= CURRENT_DATE - 7",
            "columns": list(self.sample_columns),
            "rows": [list(r) for r in self.sample_rows],
            "row_count": len(self.sample_rows),
        }


@dataclass(frozen=True)
class EChartsRenderFixture:
    """v1 §1 `echarts_render` 业务 Tool 的 mock 数据。

    输出是 ECharts option dict（前端直接消费）。
    """

    name: str = "echarts_render"
    sample_title: str = "近 7 天活跃用户数"

    def input(self) -> dict[str, Any]:
        return {
            "data": {
                "columns": ["day", "active_users"],
                "rows": [["2026-07-15", 1234], ["2026-07-16", 1302]],
            },
            "chart_type": "line",
            "title": self.sample_title,
        }

    def output(self) -> dict[str, Any]:
        return {
            "title": {"text": self.sample_title},
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": ["2026-07-15", "2026-07-16"]},
            "yAxis": {"type": "value"},
            "series": [{"type": "line", "data": [1234, 1302]}],
        }


@dataclass(frozen=True)
class MemorySaveFixture:
    """v1 §1 `memory_save` 业务 Tool 的 mock 数据。"""

    name: str = "memory_save"
    sample_content: str = "用户偏好简洁回答"
    sample_user_id: str = "user-001"

    def input(self, content: str | None = None) -> dict[str, Any]:
        return {
            "content": content if content is not None else self.sample_content,
            "user_id": self.sample_user_id,
            "tags": ["preference"],
        }

    def output(self) -> dict[str, Any]:
        return {
            "memory_id": "mem-7f3a",
            "content_hash": "sha256:abcd1234",
            "stored_at": "2026-07-22T10:00:00Z",
        }


@dataclass(frozen=True)
class MemoryRecallFixture:
    """v1 §1 `memory_recall` 业务 Tool 的 mock 数据。"""

    name: str = "memory_recall"
    sample_query: str = "用户偏好什么回答风格"
    sample_user_id: str = "user-001"

    def input(self, query: str | None = None) -> dict[str, Any]:
        return {
            "query": query if query is not None else self.sample_query,
            "user_id": self.sample_user_id,
            "top_k": 3,
        }

    def output(self) -> dict[str, Any]:
        return {
            "query": self.sample_query,
            "results": [
                {
                    "memory_id": "mem-7f3a",
                    "content": "用户偏好简洁回答",
                    "score": 0.91,
                },
                {
                    "memory_id": "mem-5b21",
                    "content": "用户偏好代码示例先行",
                    "score": 0.74,
                },
            ],
            "hit": True,
        }


@dataclass(frozen=True)
class BusinessToolFixture:
    """6 个业务 Tool fixture 的容器。"""

    web_search: WebSearchFixture = field(default_factory=WebSearchFixture)
    rag_query: RagQueryFixture = field(default_factory=RagQueryFixture)
    query_database: QueryDatabaseFixture = field(default_factory=QueryDatabaseFixture)
    echarts_render: EChartsRenderFixture = field(default_factory=EChartsRenderFixture)
    memory_save: MemorySaveFixture = field(default_factory=MemorySaveFixture)
    memory_recall: MemoryRecallFixture = field(default_factory=MemoryRecallFixture)

    # 6 个 Tool 名（与 v1 §1 锁定一致）
    @property
    def all_names(self) -> tuple[str, ...]:
        return (
            self.web_search.name,
            self.rag_query.name,
            self.query_database.name,
            self.echarts_render.name,
            self.memory_save.name,
            self.memory_recall.name,
        )


# 工厂函数（与 __init__.py 的导出对齐）
def make_fixtures() -> BusinessToolFixture:
    """构造一个完整的 6-Tool fixture 容器。"""
    return BusinessToolFixture()
