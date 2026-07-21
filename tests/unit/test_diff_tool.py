from __future__ import annotations

from pathlib import Path

from kama_claude.core.tools.builtin.diff_tool import DiffTool


# 功能：验证两个内容不同的文件能生成包含 +/- 标记的统一差异格式
# 设计：一个文件改了一行，断言输出里同时有以 "-" 开头的旧行和以 "+" 开头的新行
async def test_diff_shows_changes(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("line1\nline2\nline3\n")
    b.write_text("line1\nCHANGED\nline3\n")
    result = await DiffTool().invoke({"path_a": str(a), "path_b": str(b)})
    assert not result.is_error
    assert "-line2" in result.content
    assert "+CHANGED" in result.content


# 功能：验证两个内容完全相同的文件返回"无差异"提示
# 设计：两个文件内容一致，断言输出明确说明没有差异，而不是返回空字符串造成误解
async def test_diff_identical_files_reports_no_diff(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("same\n")
    b.write_text("same\n")
    result = await DiffTool().invoke({"path_a": str(a), "path_b": str(b)})
    assert not result.is_error
    assert "no difference" in result.content.lower()
