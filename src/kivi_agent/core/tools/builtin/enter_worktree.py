from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.tools.base import BaseTool, ToolResult
from kivi_agent.core.workspace.worktree import create_worktree


class EnterWorktreeParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    repo_root: str
    name: str
    base_branch: str = "HEAD"


class EnterWorktreeTool(BaseTool):
    params_model = EnterWorktreeParams
    name = "enter_worktree"
    description = (
        "Create an isolated Git worktree for a task, on its own branch, so file edits and "
        "commands don't touch the main working directory. Returns the absolute path of the "
        "new worktree — use that path as the base for subsequent file and bash operations "
        "for this task (this tool does not change the process's current directory)."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "repo_root": {"type": "string", "description": "Path to the main Git repository."},
            "name": {
                "type": "string",
                "description": "Short task name, used to derive branch/dir name.",
            },
            "base_branch": {
                "type": "string",
                "description": "Branch to base the worktree on (default HEAD).",
            },
        },
        "required": ["repo_root", "name"],
    }

    # 为任务创建独立 Git 工作树，返回其绝对路径供后续工具调用使用
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = EnterWorktreeParams.model_validate(params)
        info = await create_worktree(Path(p.repo_root), p.name, p.base_branch)
        return ToolResult(
            content=f"created isolated worktree on branch {info.branch}\n{info.path}"
        )
