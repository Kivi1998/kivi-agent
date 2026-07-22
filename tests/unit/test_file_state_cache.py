from __future__ import annotations

from pathlib import Path

from kivi_agent.core.tools.file_state_cache import FileStateCache


# 功能：验证 record 后 is_stale 返回 False（未变化）
# 设计：写文件→record→is_stale，覆盖"刚记录就检查"这条基线
def test_record_then_is_stale_returns_false(tmp_path: Path) -> None:
    cache = FileStateCache()
    f = tmp_path / "x.txt"
    f.write_text("hello")
    cache.record(f)
    assert cache.has(f) is True
    assert cache.is_stale(f) is False


# 功能：验证文件被外部修改后 is_stale 返回 True
# 设计：record 后改写文件内容，断言 is_stale=True，覆盖"检测到变化"这条核心路径
def test_is_stale_detects_modification(tmp_path: Path) -> None:
    cache = FileStateCache()
    f = tmp_path / "x.txt"
    f.write_text("hello")
    cache.record(f)
    f.write_text("modified content that is different")
    assert cache.is_stale(f) is True


# 功能：验证从未 record 过的文件 is_stale 返回 False（默认视为新鲜）
# 设计：edit_file 在没有 read_file 记录的情况下不应该误报 stale；
#      这条规则保护"我直接编辑一个新文件"的合法用例
def test_unrecorded_file_is_not_stale(tmp_path: Path) -> None:
    cache = FileStateCache()
    f = tmp_path / "never_read.txt"
    f.write_text("hello")
    assert cache.has(f) is False
    assert cache.is_stale(f) is False


# 功能：验证 invalidate 后 is_stale 重新返回 False（清掉旧记录）
# 设计：覆盖"显式让缓存忘记这个文件"的语义，read_file 失败/重读时调用
def test_invalidate_clears_record(tmp_path: Path) -> None:
    cache = FileStateCache()
    f = tmp_path / "x.txt"
    f.write_text("hello")
    cache.record(f)
    f.write_text("modified")
    assert cache.is_stale(f) is True
    cache.invalidate(f)
    assert cache.has(f) is False
    assert cache.is_stale(f) is False


# 功能：验证文件被删除后 is_stale 返回 True；missing path 调 record 不抛异常且 size=0
# 设计：先 record 已有文件（5 字节），删除后 is_stale 必须报告"之前有现在没了"；
#      再 record 同一个 path，cache 内部调 stat 不抛异常，记 size=0 标记
def test_record_handles_missing_file(tmp_path: Path) -> None:
    cache = FileStateCache()
    f = tmp_path / "ghost.txt"
    f.write_text("hello")
    cache.record(f)
    f.unlink()
    # 1) is_stale 检测到文件被删（之前有 size=5 现在没了）
    assert cache.is_stale(f) is True
    # 2) record 不抛异常，size=0 标记"曾经存在但现在不在"
    state = cache.record(f)
    assert state.size == 0
