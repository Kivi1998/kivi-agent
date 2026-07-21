from __future__ import annotations

from pathlib import Path

import pytest

from kama_claude.core.tools.builtin.edit_file import EditFileTool


# 功能：验证唯一匹配时能正确替换并原子写回文件
# 设计：写入含唯一目标字符串的文件，替换后重新读取文件内容，确认落盘结果而非只看返回值
async def test_edit_unique_match_replaces(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("def foo():\n    return 1\n")
    result = await EditFileTool().invoke(
        {"path": str(f), "old_string": "return 1", "new_string": "return 2"}
    )
    assert not result.is_error
    assert f.read_text() == "def foo():\n    return 2\n"


# 功能：验证 old_string 在文件中不存在时返回错误而不是静默无操作
# 设计：传入文件中不存在的字符串，断言 is_error 为 True 且文件内容未被改动
async def test_edit_no_match_returns_error(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    original = "def foo():\n    return 1\n"
    f.write_text(original)
    result = await EditFileTool().invoke(
        {"path": str(f), "old_string": "return 999", "new_string": "return 2"}
    )
    assert result.is_error
    assert f.read_text() == original


# 功能：验证 old_string 匹配多处时拒绝执行，避免改错地方
# 设计：文件里放两处相同字符串，断言返回错误且提示"not unique"，文件内容不变
async def test_edit_ambiguous_match_returns_error(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    original = "x = 1\nx = 1\n"
    f.write_text(original)
    result = await EditFileTool().invoke(
        {"path": str(f), "old_string": "x = 1", "new_string": "x = 2"}
    )
    assert result.is_error
    assert "unique" in result.content.lower()
    assert f.read_text() == original


# 功能：验证路径穿越（含 ..）被拒绝
# 设计：与 read_file/write_file 保持一致的安全边界，传入 "../secret.py" 断言抛出 PermissionError
async def test_edit_path_traversal_raises() -> None:
    with pytest.raises(PermissionError):
        await EditFileTool().invoke(
            {"path": "../secret.py", "old_string": "a", "new_string": "b"}
        )
