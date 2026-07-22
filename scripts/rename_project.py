#!/usr/bin/env python3
"""一次性重命名脚本：KamaClaude → kivi-agent。

策略：word-boundary 替换，按最长前缀优先避免部分匹配。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# 替换顺序：先长后短，避免 kama 误吃 kama_claude 等
REPLACEMENTS: list[tuple[str, str]] = [
    ("kama_claude", "kivi_agent"),
    ("KamaClaude", "kivi-agent"),
    ("kama-core", "kivi-core"),
    ("kama-tui", "kivi-tui"),
    ("kama", "kivi"),
]

# 不动的目录
EXCLUDE_DIRS = {".venv", ".git", "__pycache__", ".ruff_cache", ".mypy_cache", ".pytest_cache", "node_modules"}
# 不动的文件后缀
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".so", ".dylib", ".dll", ".bin", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".tar", ".gz", ".whl", ".egg-info"}
# 排除的邮箱/域名等
EXCLUDE_LINES_PATTERNS = [
    re.compile(r"agent@kamaclaude\.local"),  # commit author email
    re.compile(r"kama_claude\.local"),
    re.compile(r"mermaid"),  # 图表
]


def is_excluded(path: Path) -> bool:
    parts = set(path.relative_to(REPO).parts)
    if parts & EXCLUDE_DIRS:
        return True
    if path.suffix in EXCLUDE_SUFFIXES:
        return True
    return False


def should_skip_line(line: str) -> bool:
    for pat in EXCLUDE_LINES_PATTERNS:
        if pat.search(line):
            return True
    return False


def replace_in_file(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, IsADirectoryError, PermissionError):
        return False
    out_lines = []
    changed = False
    for line in text.splitlines(keepends=True):
        if should_skip_line(line):
            out_lines.append(line)
            continue
        new_line = line
        for old, new in REPLACEMENTS:
            new_line = re.sub(r"\b" + re.escape(old) + r"\b", new, new_line)
        if new_line != line:
            changed = True
        out_lines.append(new_line)
    if changed:
        path.write_text("".join(out_lines), encoding="utf-8")
    return changed


def get_tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    files = []
    for rel in result.stdout.splitlines():
        p = REPO / rel
        if p.is_file() and not is_excluded(p):
            files.append(p)
    return files


def main() -> int:
    files = get_tracked_files()
    print(f"扫描 {len(files)} 个 tracked 文件")
    changed = []
    for f in files:
        if replace_in_file(f):
            changed.append(f)
    print(f"修改 {len(changed)} 个文件")
    for f in changed[:30]:
        print(f"  - {f.relative_to(REPO)}")
    if len(changed) > 30:
        print(f"  ... + {len(changed) - 30} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
