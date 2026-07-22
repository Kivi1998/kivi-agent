"""memory_recall 业务 Tool（agent: package-c-v1）。

按 docs/contracts/v1.md §1 冻结名 = memory_recall（旧名 recall_memory 已弃用）。
按 C 报告 §6.10 决议：按 query 召回相关记忆（演示版 substring 匹配 + importance 加权）。
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kivi_agent.core.business.base import BaseBusinessTool
from kivi_agent.core.business.memory_backend import LongTermMemoryBackend
from kivi_agent.core.tools.base import ToolResult


# memory_recall 输入参数（agent: package-c-v1）
class MemoryRecallParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    query: str = Field(min_length=1)  # 必填，至少 1 字符
    top_k: int = Field(default=5, ge=1, le=100)  # 1-100，默认 5


# memory_recall 业务 Tool：演示版 substring 匹配（agent: package-c-v1）
class MemoryRecallTool(BaseBusinessTool):
    """memory_recall Tool：按 query 召回 top-K 条记忆。

    演示版：
    - 扫描 ~/.kivi/memory/ 下所有 .md
    - query 与 content 简单 substring 匹配
    - 评分：命中次数 × importance 权重
    - 按 score 倒序返回 top_k
    - category=read（只读）

    真实实现：调 ES kNN 召回 + Reranker（C 报告 §6.5）。
    """

    # 默认根目录：~/.kivi/memory/（与 memory_save 共享）
    DEFAULT_ROOT: Path = Path("~/.kivi/memory")

    params_model = MemoryRecallParams
    name = "memory_recall"
    category = "read"  # 只读，无副作用
    description = (
        "Recall long-term memories that match the given query. "
        "Scans ~/.kivi/memory/ for matching entries and returns up to top_k "
        "results sorted by relevance (substring match count × importance weight). "
        "Use this when the user asks questions that may be answered by previously "
        "saved facts, preferences, decisions, or instructions."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The recall query (natural language).",
                "minLength": 1,
            },
            "top_k": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "default": 5,
                "description": "Maximum number of memories to return. Default 5.",
            },
        },
        "required": ["query"],
    }

    # 初始化：可注入自定义根目录（与 memory_save 共享）
    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self._backend = LongTermMemoryBackend(root or self.DEFAULT_ROOT)

    # 演示版入口（agent: package-c-v1）
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        try:
            p = MemoryRecallParams.model_validate(params)
        except ValidationError as e:
            return ToolResult(
                content=json.dumps({"error": "invalid_params", "detail": e.errors()}, ensure_ascii=False),
                is_error=True,
                error_type="schema_error",
            )
        results = self._backend.recall(p.query, top_k=p.top_k)
        return ToolResult(
            content=json.dumps(
                {
                    "query": p.query,
                    "top_k": p.top_k,
                    "count": len(results),
                    "memories": [
                        {
                            "memory_id": e.memory_id,
                            "memory_type": e.memory_type,
                            "importance": e.importance,
                            "status": e.status,
                            "created_at": e.created_at,
                            "content": e.content,
                            "filename": e.filename,
                        }
                        for e in results
                    ],
                },
                ensure_ascii=False,
            )
        )

    @property
    def backend(self) -> LongTermMemoryBackend:
        return self._backend
