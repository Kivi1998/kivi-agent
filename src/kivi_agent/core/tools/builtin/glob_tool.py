from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.tools.base import BaseTool, ToolResult
from kivi_agent.core.tools.builtin._fs_filters import is_skipped

_MAX_RESULTS = 200


class GlobParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pattern: str
    path: str = "."


class GlobTool(BaseTool):
    params_model = GlobParams
    name = "glob"
    category = "read"
    description = (
        "Find files by name pattern (e.g. '**/*.py', 'src/*.ts'). "
        "Results are sorted by modification time, most recent first. "
        "Skips .git, .venv, node_modules and other common noise directories."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern, e.g. '**/*.py'.",
            },
            "path": {
                "type": "string",
                "description": "Base directory to search from (default '.').",
            },
        },
        "required": ["pattern"],
    }

    # 按 glob 模式搜索文件名，跳过噪音目录，按 mtime 倒序返回相对路径列表
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = GlobParams.model_validate(params)
        base = Path(p.path)

        if ".." in base.parts:
            raise PermissionError(f"path traversal not allowed: {p.path}")

        matches = [
            f for f in base.glob(p.pattern)
            if f.is_file() and not is_skipped(f.parts)
        ]
        matches.sort(key=lambda f: f.stat().st_mtime, reverse=True)

        if not matches:
            return ToolResult(content=f"no matches for pattern: {p.pattern}")

        truncated = len(matches) > _MAX_RESULTS
        shown = matches[:_MAX_RESULTS]
        lines = [str(f) for f in shown]
        if truncated:
            lines.append(f"[truncated: showing {_MAX_RESULTS} of {len(matches)} matches]")

        return ToolResult(content="\n".join(lines))
