from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kama_claude.core.tools.base import BaseTool, ToolResult
from kama_claude.core.workspace.worktree import WorktreeInfo, remove_worktree


class ExitWorktreeParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    repo_root: str
    path: str
    branch: str


class ExitWorktreeTool(BaseTool):
    params_model = ExitWorktreeParams
    name = "exit_worktree"
    description = (
        "Discard a task's isolated worktree created by enter_worktree: removes the worktree "
        "directory and deletes its branch. Any uncommitted changes in that worktree are lost — "
        "make sure the work has been committed or is no longer needed before calling this."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "repo_root": {"type": "string", "description": "Path to the main Git repository."},
            "path": {"type": "string", "description": "Worktree path returned by enter_worktree."},
            "branch": {"type": "string", "description": "Worktree branch name returned by enter_worktree."},
        },
        "required": ["repo_root", "path", "branch"],
    }

    # 移除指定的 Git 工作树目录及其分支
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = ExitWorktreeParams.model_validate(params)
        info = WorktreeInfo(path=Path(p.path), branch=p.branch, base_branch="")
        await remove_worktree(Path(p.repo_root), info, force=True)
        return ToolResult(content=f"removed worktree {p.path} and branch {p.branch}")
