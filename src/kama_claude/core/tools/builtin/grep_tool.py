from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kama_claude.core.tools.base import BaseTool, ToolResult
from kama_claude.core.tools.builtin._fs_filters import is_skipped

_MAX_MATCHES = 200


class GrepParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pattern: str
    path: str = "."
    include: str = "**/*"


class GrepTool(BaseTool):
    params_model = GrepParams
    name = "grep"
    category = "read"
    description = (
        "Search file contents with a regular expression. "
        "Optionally restrict to files matching an include glob (e.g. '*.py'). "
        "Returns matches as 'file:line:content', truncated at 200 matches."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regular expression to search for.",
            },
            "path": {
                "type": "string",
                "description": "Base directory to search from (default '.').",
            },
            "include": {
                "type": "string",
                "description": "Glob to filter which files are searched (default '**/*').",
            },
        },
        "required": ["pattern"],
    }

    # 在指定目录下按正则搜索文件内容，返回 file:line:content 格式的命中列表
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = GrepParams.model_validate(params)
        base = Path(p.path)

        if ".." in base.parts:
            raise PermissionError(f"path traversal not allowed: {p.path}")

        try:
            regex = re.compile(p.pattern)
        except re.error as exc:
            return ToolResult(
                content=f"invalid regex: {exc}",
                is_error=True,
                error_type="schema_error",
            )

        matches: list[str] = []
        for f in base.glob(p.include):
            if not f.is_file() or is_skipped(f.parts):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{f}:{lineno}:{line.strip()}")
                    if len(matches) >= _MAX_MATCHES:
                        break
            if len(matches) >= _MAX_MATCHES:
                break

        if not matches:
            return ToolResult(content=f"no matches for pattern: {p.pattern}")

        content = "\n".join(matches)
        if len(matches) >= _MAX_MATCHES:
            content += f"\n[truncated: showing first {_MAX_MATCHES} matches]"

        return ToolResult(content=content)
