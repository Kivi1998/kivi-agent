from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from kama_claude.core.tools.builtin.enter_worktree import EnterWorktreeTool
from kama_claude.core.tools.builtin.exit_worktree import ExitWorktreeTool


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


# 功能：验证 EnterWorktreeTool 返回的路径确实是新建的独立工作树目录
# 设计：调用工具后断言返回内容里的路径存在且含仓库文件，说明工作树创建成功
async def test_enter_worktree_returns_isolated_path(repo: Path) -> None:
    result = await EnterWorktreeTool().invoke({"repo_root": str(repo), "name": "demo task"})
    assert not result.is_error
    path_str = result.content.strip().splitlines()[-1]
    assert Path(path_str).exists()
    assert (Path(path_str) / "README.md").exists()


# 功能：验证 ExitWorktreeTool 能按路径把工作树清理掉
# 设计：先 enter 再 exit，断言 exit 后目录不存在，形成完整生命周期闭环
async def test_exit_worktree_removes_directory(repo: Path) -> None:
    enter_result = await EnterWorktreeTool().invoke({"repo_root": str(repo), "name": "demo task 2"})
    path_str = enter_result.content.strip().splitlines()[-1]
    exit_result = await ExitWorktreeTool().invoke(
        {"repo_root": str(repo), "path": path_str, "branch": f"kama-agent-{'demo-task-2'}"}
    )
    assert not exit_result.is_error
    assert not Path(path_str).exists()
