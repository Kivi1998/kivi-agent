from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(kw_only=True)
class RunContext:
    """运行参数上下文。Wave 1 起按 v1 契约冻结（docs/contracts/v1.md §2）。

    字段集合已冻结为 v1。A/B/C/D/E 各阶段需要的扩展字段必须走 ADR + schema_version 升级。
    kw_only=True 是为了让有默认值的 schema_version / 可选 ID 字段在 Python dataclass 语义下
    也能与必填字段共存，不强制要求调用方按字段顺序传参。
    """

    schema_version: int = 1
    run_id: str
    trace_id: str
    user_id: str
    session_id: str
    datasource_id: str | None = None
    knowledge_base_id: str | None = None
    frontend_connection_id: str | None = None
    runtime_values: dict[str, Any] = field(default_factory=dict)
