from __future__ import annotations

from pathlib import Path

import pytest

from kivi_agent.core.tools.builtin.edit_file import EditFileTool
from kivi_agent.core.tools.file_state_cache import FileStateCache


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


# 功能：验证未注入 cache 时 edit_file 不做 staleness 检查（不破坏现有行为）
# 设计：用现有 4 个用例之一的写入模式编辑文件，不传 cache，断言 is_error=False，
#      覆盖"可选 cache 不影响默认路径"
async def test_edit_without_cache_works(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    tool = EditFileTool()  # 不传 cache
    result = await tool.invoke({"path": str(f), "old_string": "x = 1", "new_string": "x = 2"})
    assert not result.is_error
    assert f.read_text() == "x = 2\n"


# 功能：验证注入 cache 后文件被外部修改时 edit_file 拒绝并返回 stale_file 错误
# 设计：先 read_file 记录状态，再让外部脚本改写文件，再调 edit_file，
#      断言返回 is_error=True 且 error_type="stale_file"，文件内容未变
async def test_edit_detects_stale_file(tmp_path: Path) -> None:
    from kivi_agent.core.tools.builtin.read_file import ReadFileTool

    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    cache = FileStateCache()
    # 1) read_file 记录状态
    await ReadFileTool(cache).invoke({"path": str(f)})
    assert cache.has(f) is True
    # 2) 外部脚本改写文件（模拟另一个进程/编辑器/用户手动编辑）
    f.write_text("x = 999\n")
    # 3) edit_file 应该检测到过期并拒绝
    result = await EditFileTool(cache).invoke(
        {"path": str(f), "old_string": "x = 1", "new_string": "x = 2"}
    )
    assert result.is_error
    assert result.error_type == "stale_file"
    # 4) 文件内容确实没被改动
    assert f.read_text() == "x = 999\n"


# 功能：验证注入 cache 但文件没被外部修改时 edit_file 正常工作
# 设计：read_file 记录后立刻 edit_file（无外部修改），断言正常替换，
#      覆盖"cache 存在但状态新鲜"的正常路径
async def test_edit_with_fresh_cache_works(tmp_path: Path) -> None:
    from kivi_agent.core.tools.builtin.read_file import ReadFileTool

    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    cache = FileStateCache()
    await ReadFileTool(cache).invoke({"path": str(f)})
    result = await EditFileTool(cache).invoke(
        {"path": str(f), "old_string": "x = 1", "new_string": "x = 2"}
    )
    assert not result.is_error
    assert f.read_text() == "x = 2\n"
