from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kama_claude.core.tools.base import BaseTool, ToolResult


class EditFileParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str
    old_string: str
    new_string: str


class EditFileTool(BaseTool):
    params_model = EditFileParams
    name = "edit_file"
    description = (
        "Replace an exact, unique occurrence of old_string with new_string in a file. "
        "Fails if old_string is not found, or if it appears more than once — "
        "include enough surrounding context in old_string to make the match unique."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to the file."},
            "old_string": {"type": "string", "description": "Exact text to replace; must be unique in the file."},
            "new_string": {"type": "string", "description": "Replacement text."},
        },
        "required": ["path", "old_string", "new_string"],
    }

    # 在文件中唯一匹配 old_string 并替换为 new_string，原子写回；未命中或多处命中时拒绝执行
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = EditFileParams.model_validate(params)

        if ".." in Path(p.path).parts:
            raise PermissionError(f"path traversal not allowed: {p.path}")

        path = Path(p.path)
        content = path.read_text(encoding="utf-8")  # raises FileNotFoundError if absent

        count = content.count(p.old_string)
        if count == 0:
            return ToolResult(
                content=f"old_string not found in {p.path}",
                is_error=True,
                error_type="runtime_error",
            )
        if count > 1:
            return ToolResult(
                content=f"old_string is not unique in {p.path}: {count} occurrences found",
                is_error=True,
                error_type="runtime_error",
            )

        new_content = content.replace(p.old_string, p.new_string, 1)
        self._atomic_write(path, new_content)

        return ToolResult(content=f"edited {p.path}")

    # 原子写入：先写同目录临时文件，再 rename 覆盖目标，避免写到一半崩溃导致文件损坏
    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
