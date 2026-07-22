from __future__ import annotations

import time
from pathlib import Path

import pytest

from kama_claude.core.filehistory.history import FileHistory


# 功能：验证 snapshot 后 list_versions 能看到一条记录且内容一致
# 设计：写文件→snapshot→list，覆盖"快照写入+读取"完整路径
def test_snapshot_and_list(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kama" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("hello")
    snap = history.snapshot(f)
    assert snap.content == b"hello"
    versions = history.list_versions(f)
    assert len(versions) == 1
    assert versions[0].version == snap.version
    assert versions[0].content == b"hello"


# 功能：验证多次 snapshot 按时间顺序保留所有版本（追加式，不覆盖）
# 设计：连续 snapshot 3 次（内容不同），断言 list 返回 3 条且时间戳单调递增
def test_multiple_snapshots_preserved_in_order(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kama" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("v1")
    s1 = history.snapshot(f)
    time.sleep(0.01)  # 确保 ts 不同
    f.write_text("v2")
    s2 = history.snapshot(f)
    time.sleep(0.01)
    f.write_text("v3")
    s3 = history.snapshot(f)
    versions = history.list_versions(f)
    assert [v.version for v in versions] == [s1.version, s2.version, s3.version]
    assert [v.content for v in versions] == [b"v1", b"v2", b"v3"]


# 功能：验证 get_version 能按 version id 取回对应快照
# 设计：写文件 v1→snapshot→改写为 v2→snapshot，然后分别 get 两条，
#      断言 content 与 snapshot 时一致
def test_get_version_returns_specific_snapshot(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kama" / "file-history")
    f = tmp_path / "x.txt"
    f.write_text("v1")
    s1 = history.snapshot(f)
    f.write_text("v2")
    s2 = history.snapshot(f)

    v1_loaded = history.get_version(f, s1.version)
    v2_loaded = history.get_version(f, s2.version)
    assert v1_loaded.content == b"v1"
    assert v2_loaded.content == b"v2"


# 功能：验证不存在的 version 抛 FileNotFoundError
# 设计：调用 get_version 传一个编造的 version id，断言异常类型便于上层工具返回明确错误
def test_get_unknown_version_raises(tmp_path: Path) -> None:
    history = FileHistory(tmp_path / ".kama" / "file-history")
    f = tmp_path / "x.txt"
    with pytest.raises(FileNotFoundError):
        history.get_version(f, "v9999")
