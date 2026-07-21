from __future__ import annotations

from pathlib import Path

from kama_claude.core.tools.builtin.grep_tool import GrepTool


# 功能：验证能在文件内容中按正则找到匹配行，输出 file:line:content 格式
# 设计：写入含目标字符串的文件，断言输出同时包含文件名、行号和命中行内容三个要素
async def test_grep_finds_match(tmp_path: Path) -> None:
    f = tmp_path / "app.py"
    f.write_text("line1\ndef target_func():\n    pass\n")
    result = await GrepTool().invoke({"pattern": "target_func", "path": str(tmp_path)})
    assert not result.is_error
    assert "app.py:2:" in result.content
    assert "target_func" in result.content


# 功能：验证 include 参数能按文件名模式限定搜索范围
# 设计：两个文件一个匹配 include 一个不匹配，断言只有匹配 include 的文件出现在结果里
async def test_grep_respects_include_filter(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("needle\n")
    (tmp_path / "b.txt").write_text("needle\n")
    result = await GrepTool().invoke(
        {"pattern": "needle", "path": str(tmp_path), "include": "*.py"}
    )
    assert "a.py" in result.content
    assert "b.txt" not in result.content


# 功能：验证无匹配时返回明确提示而不是报错
# 设计：搜索一个不存在的字符串，断言 is_error 为 False 且提示信息可读
async def test_grep_no_match_returns_message(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("hello\n")
    result = await GrepTool().invoke({"pattern": "nonexistent_xyz", "path": str(tmp_path)})
    assert not result.is_error
    assert "no matches" in result.content.lower()
