from __future__ import annotations

from pathlib import Path

import pytest

from kivi_agent.core.filehistory.history import FileHistory
from kivi_agent.core.tools.builtin.rewind_file import RewindFileTool


# 功能：验证 rewind 把文件内容还原到指定 version 的快照
# 设计：写 v1→snapshot→改写为 v2→snapshot→改写为 v3，调 rewind(v1)，
#      断言文件内容回到 v1；不依赖工具直接测 FileHistory.rewind 也行，但用工具覆盖端到端
async def test_rewind_restores_to_target_version(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("v1")
    s1 = history.snapshot(f)
    f.write_text("v2")
    history.snapshot(f)
    f.write_text("v3 (current, broken)")

    tool = RewindFileTool(history)
    result = await tool.invoke({"path": str(f), "version": s1.version})
    assert not result.is_error
    assert f.read_text() == "v1"


# 功能：验证 path 不在 history 里时返回明确错误
# 设计：snapshot 一个文件、创建另一个未 snapshot 的文件、rewind 它，断言 is_error=True
#      覆盖"目标文件没有历史记录"这条边界（不会创建空快照）
async def test_rewind_unknown_path_returns_error(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("hello")
    # 不 snapshot，直接 rewind → 应报错而不是悄悄创建空快照
    tool = RewindFileTool(history)
    result = await tool.invoke({"path": str(f), "version": "v1"})
    assert result.is_error
    assert "no history" in result.content.lower() or "not found" in result.content.lower()


# 功能：验证 version 不存在时返回明确错误
# 设计：snapshot 一次但 rewind 一个不存在的 version，断言 is_error=True
async def test_rewind_unknown_version_returns_error(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("v1")
    history.snapshot(f)
    tool = RewindFileTool(history)
    result = await tool.invoke({"path": str(f), "version": "v9999"})
    assert result.is_error
    assert result.error_type == "runtime_error"


# 功能：验证 path 中包含 .. 时抛 PermissionError
# 设计：与既有 edit_file / read_file 保持一致的安全边界
async def test_rewind_path_traversal_raises(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    tool = RewindFileTool(history)
    with pytest.raises(PermissionError):
        await tool.invoke({"path": "../etc/passwd", "version": "v1"})


# 功能：验证 rewind 后该文件原本的当前内容也作为一个新快照被自动保存
# 设计：先做 s1（v1）、改写为 v2、rewind 到 s1，断言多出一条快照（rewind 前自动备份）
#      这样"连续 rewind 不会丢版本"，回滚本身也可回滚
async def test_rewind_creates_snapshot_of_pre_rewind_state(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kivi" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("v1")
    s1 = history.snapshot(f)
    f.write_text("v2 broken")
    tool = RewindFileTool(history, snapshot_before_rewind=True)
    result = await tool.invoke({"path": str(f), "version": s1.version})
    assert not result.is_error
    versions = history.list_versions(f)
    # 至少 2 个版本：s1（v1）和 rewind 前自动存的 v2 快照
    assert len(versions) >= 2
    assert versions[-1].content == b"v2 broken"
