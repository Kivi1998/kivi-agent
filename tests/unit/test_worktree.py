from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from kivi_agent.core.workspace.worktree import create_worktree, remove_worktree, slugify


# 每个测试用例在 tmp_path 下建一个最小可用的 git 仓库并提交一次
@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


# 功能：验证任意任务名能生成合法的 git 分支/目录 slug（小写、无空格、无特殊字符）
# 设计：传入含空格和大写字母的任务名，断言输出只含小写字母数字和连字符
def test_slugify_normalizes_name() -> None:
    assert slugify("Fix Login Bug!!") == "fix-login-bug"


# 功能：验证 create_worktree 能在仓库下创建独立目录和分支，且新目录包含仓库文件
# 设计：调用后检查返回的 WorktreeInfo.path 存在且含 README.md，同时用 git worktree list 交叉验证分支确实被 git 记录
async def test_create_worktree_creates_isolated_dir(repo: Path) -> None:
    info = await create_worktree(repo, "task one")
    assert info.path.exists()
    assert (info.path / "README.md").exists()
    listing = subprocess.run(
        ["git", "worktree", "list"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert str(info.path) in listing


# 功能：验证 remove_worktree 能干净回收工作树目录和对应分支
# 设计：先创建再移除，断言目录不再存在，且 git worktree list 里也不再出现该分支
async def test_remove_worktree_cleans_up(repo: Path) -> None:
    info = await create_worktree(repo, "task two")
    await remove_worktree(repo, info, force=True)
    assert not info.path.exists()
    listing = subprocess.run(
        ["git", "worktree", "list"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout
    assert str(info.path) not in listing
