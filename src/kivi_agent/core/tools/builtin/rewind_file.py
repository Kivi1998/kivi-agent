from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kivi_agent.core.filehistory.history import FileHistory
from kivi_agent.core.tools.base import BaseTool, ToolResult


class RewindFileParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: str
    version: str


# rewind_file 工具：把文件还原到 FileHistory 中的某个快照版本
class RewindFileTool(BaseTool):
    params_model = RewindFileParams
    name = "rewind_file"
    category = "write"  # 还原会覆盖目标文件，属于写操作
    description = (
        "Restore a file to a previous snapshot version created by edit_file or write_file. "
        "Use `list_file_versions` first to see available versions, then pass the chosen "
        "version id. By default a snapshot of the current (about-to-be-overwritten) "
        "content is taken first, so the rewind itself is reversible."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Relative path to the file (relative to cwd).",
            },
            "version": {
                "type": "string",
                "description": "Version id returned by list_file_versions.",
            },
        },
        "required": ["path", "version"],
    }

    # 初始化：注入 FileHistory；snapshot_before_rewind 控制是否在还原前自动备份当前内容
    def __init__(self, file_history: FileHistory, *, snapshot_before_rewind: bool = True) -> None:
        super().__init__()
        self._history = file_history
        self._snapshot_before = snapshot_before_rewind

    # 还原文件到指定 version；目标文件无历史时返回明确错误而不是抛 FileNotFoundError
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = RewindFileParams.model_validate(params)

        if ".." in Path(p.path).parts:
            raise PermissionError(f"path traversal not allowed: {p.path}")

        path = Path(p.path)
        # 目标文件没有过任何快照：明确告知，避免悄悄创建空快照
        if not self._history.list_versions(path):
            return ToolResult(
                content=(
                    f"no history for {p.path}; "
                    "cannot rewind a file that has never been snapshotted"
                ),
                is_error=True,
                error_type="runtime_error",
            )

        # 自动备份当前内容（rewind 本身也可回滚）
        if self._snapshot_before:
            self._history.snapshot(path)

        try:
            self._history.rewind(path, p.version)
        except FileNotFoundError as exc:
            return ToolResult(content=str(exc), is_error=True, error_type="runtime_error")

        return ToolResult(content=f"rewound {p.path} to version {p.version}")
