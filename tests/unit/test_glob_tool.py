from __future__ import annotations

from pathlib import Path

from kama_claude.core.tools.builtin.glob_tool import GlobTool


# 功能：验证按 *.py 模式能搜到匹配文件，按 mtime 倒序排列
# 设计：写两个文件并控制 mtime 顺序，断言更晚修改的文件排在前面，覆盖排序这一核心行为
async def test_glob_matches_and_sorts_by_mtime(tmp_path: Path) -> None:
    old = tmp_path / "old.py"
    old.write_text("x")
    new = tmp_path / "new.py"
    new.write_text("y")
    import os
    import time

    os.utime(old, (time.time() - 100, time.time() - 100))
    result = await GlobTool().invoke({"pattern": "*.py", "path": str(tmp_path)})
    lines = result.content.splitlines()
    assert lines[0].endswith("new.py")
    assert lines[1].endswith("old.py")


# 功能：验证 .git 等目录下的文件不会出现在结果里
# 设计：在 .git 子目录放一个同样匹配 pattern 的文件，断言结果里不包含它，覆盖 SKIP_DIRS 过滤
async def test_glob_skips_git_dir(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hooks.py").write_text("x")
    (tmp_path / "real.py").write_text("y")
    result = await GlobTool().invoke({"pattern": "**/*.py", "path": str(tmp_path)})
    assert "real.py" in result.content
    assert "hooks.py" not in result.content


# 功能：验证无匹配时返回明确的"无结果"提示而不是空字符串
# 设计：空目录搜索，断言 content 非空且包含"no match"类字样，避免下游 LLM 把空字符串误判为工具异常
async def test_glob_no_match_returns_message(tmp_path: Path) -> None:
    result = await GlobTool().invoke({"pattern": "*.nonexistent", "path": str(tmp_path)})
    assert not result.is_error
    assert "no match" in result.content.lower()
