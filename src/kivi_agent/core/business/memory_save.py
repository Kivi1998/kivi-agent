"""memory_save 业务 Tool（agent: package-c-v1）。

按 docs/contracts/v1.md §1 冻结名 = memory_save（旧名 note_save 已弃用）。
按 C 报告 §6.6 决议：写 v1 4 字段 frontmatter（memory_type / importance / status / created_at）。
按 C 报告 §3.1 写入路径：~/.kivi/memory/。

演示版：纯本地文件存储，无 ES / 无 embedding。
未来切真 VectorMemoryBackend 时（C 报告 §6.3），替换 LongTermMemoryBackend 实现。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from kivi_agent.core.business.base import BaseBusinessTool
from kivi_agent.core.business.memory_backend import LongTermMemoryBackend, LongTermMemoryEntry
from kivi_agent.core.tools.base import ToolResult


# v1 长期记忆类型（按 C 报告 §6.6 与 aigroup 对齐 + kivi 已有 reference）
MemoryTypeLiteral = Literal["fact", "preference", "decision", "instruction", "correction", "summary", "reference"]


# memory_save 输入参数（agent: package-c-v1）
class MemorySaveParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    content: str = Field(min_length=1)  # 必填，至少 1 字符
    memory_type: MemoryTypeLiteral = "fact"  # 默认 fact
    importance: int = Field(default=5, ge=1, le=10)  # 1-10，默认 5


# memory_save 业务 Tool：演示版写本地 Markdown（agent: package-c-v1）
class MemorySaveTool(BaseBusinessTool):
    """memory_save Tool：写入长期记忆到 ~/.kivi/memory/。

    演示版：
    - 写入路径：~/.kivi/memory/<timestamp>_<id>.md
    - frontmatter：memory_id / memory_type / importance / status / created_at
    - 初始 status=active
    - category=write（有副作用：写文件）

    写入是写操作，默认 ASK 提醒用户（按 v1 §7.2 + C 报告"演示场景通过项目级
    .kivi/config.toml 一次性放行"约定）。
    """

    # 默认根目录：~/.kivi/memory/
    DEFAULT_ROOT: Path = Path("~/.kivi/memory")

    params_model = MemorySaveParams
    name = "memory_save"
    category = "write"  # 写入文件，有副作用
    description = (
        "Save a long-term memory entry to ~/.kivi/memory/. "
        "Memory is persisted as Markdown with YAML frontmatter (memory_id, "
        "memory_type, importance, status, created_at). "
        "Use this when the user shares a fact, preference, decision, instruction, "
        "correction, or summary that should be remembered across sessions. "
        "Memory types: fact, preference, decision, instruction, correction, summary, reference. "
        "Importance is 1-10 (default 5). Higher importance gets weighted higher in recall."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The memory content (Markdown allowed).",
                "minLength": 1,
            },
            "memory_type": {
                "type": "string",
                "enum": ["fact", "preference", "decision", "instruction", "correction", "summary", "reference"],
                "default": "fact",
                "description": "Memory type. Default: fact.",
            },
            "importance": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 5,
                "description": "Importance 1-10. Default 5. Higher values rank higher in recall.",
            },
        },
        "required": ["content"],
    }

    # 初始化：可注入自定义根目录（默认 ~/.kivi/memory/）
    def __init__(self, root: Path | None = None) -> None:
        super().__init__()
        self._backend = LongTermMemoryBackend(root or self.DEFAULT_ROOT)

    # 演示版入口（agent: package-c-v1）
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        try:
            p = MemorySaveParams.model_validate(params)
        except ValidationError as e:
            return ToolResult(
                content=json.dumps({"error": "invalid_params", "detail": e.errors()}, ensure_ascii=False),
                is_error=True,
                error_type="schema_error",
            )
        created_at = LongTermMemoryBackend.now_iso()
        memory_id = LongTermMemoryBackend.make_memory_id(
            content=p.content, memory_type=p.memory_type, created_at=created_at
        )
        entry = LongTermMemoryEntry(
            memory_id=memory_id,
            memory_type=p.memory_type,
            importance=p.importance,
            status="active",  # 初始 active
            created_at=created_at,
            content=p.content,
        )
        path = self._backend.save(entry)
        return ToolResult(
            content=json.dumps(
                {
                    "memory_id": memory_id,
                    "memory_type": p.memory_type,
                    "importance": p.importance,
                    "status": "active",
                    "created_at": created_at,
                    "path": str(path),
                },
                ensure_ascii=False,
            )
        )

    @property
    def backend(self) -> LongTermMemoryBackend:
        return self._backend
