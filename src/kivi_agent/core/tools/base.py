from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from pydantic import BaseModel


@dataclass
class ToolResult:
    content: str
    is_error: bool = False
    # "runtime_error" | "timeout" | "schema_error" | "permission_denied"
    error_type: str | None = None


class BaseTool(ABC):
    name: str
    description: str
    # v1 §4 契约：所有 BaseTool 子类必须有 input_schema。空 dict 表示"不暴露参数"。
    # 具体子类必须 override 此属性。
    input_schema: dict[str, object] = {}
    params_model: ClassVar[type[BaseModel] | None] = None
    # 工具分类："read"（只读，可并发）｜"write"（改写文件状态）｜"command"（任意命令执行）｜"other"（默认）
    category: ClassVar[str] = "other"

    # 执行工具调用，返回结果或错误
    @abstractmethod
    async def invoke(self, params: dict[str, object]) -> ToolResult: ...
