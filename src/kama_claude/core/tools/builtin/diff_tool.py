from __future__ import annotations

import difflib
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kama_claude.core.tools.base import BaseTool, ToolResult

_MAX_DIFF_LINES = 200


class DiffParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path_a: str
    path_b: str


class DiffTool(BaseTool):
    params_model = DiffParams
    name = "diff"
    description = (
        "Show a unified diff between two files (e.g. a file before and after an edit, "
        "or a file in the main worktree vs a task worktree). Output truncated at 200 lines."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "path_a": {"type": "string", "description": "Path to the 'before' file."},
            "path_b": {"type": "string", "description": "Path to the 'after' file."},
        },
        "required": ["path_a", "path_b"],
    }

    # 生成两个文件的统一差异（unified diff），无差异时返回明确提示
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = DiffParams.model_validate(params)
        a_lines = Path(p.path_a).read_text(encoding="utf-8").splitlines(keepends=True)
        b_lines = Path(p.path_b).read_text(encoding="utf-8").splitlines(keepends=True)

        diff_lines = list(
            difflib.unified_diff(a_lines, b_lines, fromfile=p.path_a, tofile=p.path_b)
        )

        if not diff_lines:
            return ToolResult(content=f"no difference between {p.path_a} and {p.path_b}")

        truncated = len(diff_lines) > _MAX_DIFF_LINES
        shown = diff_lines[:_MAX_DIFF_LINES]
        content = "".join(shown)
        if truncated:
            content += f"\n[truncated: showing first {_MAX_DIFF_LINES} lines]"

        return ToolResult(content=content)
