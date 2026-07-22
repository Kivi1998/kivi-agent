from __future__ import annotations

# 搜索类工具（glob/grep）统一跳过的目录名
SKIP_DIRS: frozenset[str] = frozenset(
    {".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", ".mypy_cache", ".pytest_cache"}
)


# 判断路径是否落在需要跳过的目录内（任一层级命中即跳过）
def is_skipped(path_parts: tuple[str, ...]) -> bool:
    return any(part in SKIP_DIRS for part in path_parts)
