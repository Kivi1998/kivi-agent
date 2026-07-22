from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class WorktreeInfo:
    path: Path
    branch: str
    base_branch: str


# 把任意字符串规范化为小写、连字符分隔、仅含字母数字的 slug，用作分支名和目录名
def slugify(name: str) -> str:
    lowered = name.lower()
    slug = _SLUG_RE.sub("-", lowered).strip("-")
    return slug or "task"


# 运行一个子进程命令，失败时抛出带 stderr 内容的 RuntimeError
async def _run_git(args: list[str], cwd: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=cwd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr.decode('utf-8', errors='replace')}")


# 为任务创建一个独立的 Git 工作树，分支名和目录名都基于 name 生成的 slug
async def create_worktree(repo_root: Path, name: str, base_branch: str = "HEAD") -> WorktreeInfo:
    slug = slugify(name)
    branch = f"kivi-agent-{slug}"
    worktree_path = repo_root / ".kivi" / "worktrees" / slug
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    await _run_git(
        ["worktree", "add", "-B", branch, str(worktree_path), base_branch],
        cwd=repo_root,
    )
    return WorktreeInfo(path=worktree_path, branch=branch, base_branch=base_branch)


# 回收工作树：先移除工作树目录，再删除对应分支；force=True 时忽略未提交改动强制移除
async def remove_worktree(repo_root: Path, info: WorktreeInfo, *, force: bool = False) -> None:
    args = ["worktree", "remove", str(info.path)]
    if force:
        args.append("--force")
    await _run_git(args, cwd=repo_root)
    await _run_git(["branch", "-D", info.branch], cwd=repo_root)
