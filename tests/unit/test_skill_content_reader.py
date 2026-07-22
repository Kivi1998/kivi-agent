"""Skills 2.0 SkillContentReader 渐进式披露测试。

启动时只读 frontmatter；read_body / read_references 延迟到调用时。
大小限制 64KB 默认 + 配置可调。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from kivi_agent.core.skills.content_reader import (
    ContentTooLargeError,
    SkillContentReader,
)


# ─────────────────────────── 辅助：造临时 skill 目录 ───────────────────────────


def _make_skill_dir(tmp_path: Path, *, body: str = "default body", references: dict[str, str] | None = None) -> Path:
    """在 tmp_path 下造一个 skill_dir（含 SKILL.md + 可选 references/）。"""
    skill_dir = tmp_path / "demo_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")
    if references:
        ref_dir = skill_dir / "references"
        ref_dir.mkdir()
        for name, content in references.items():
            (ref_dir / name).write_text(content, encoding="utf-8")
    return skill_dir


# ─────────────────────────── read_body ───────────────────────────


# 功能：read_body 读取 SKILL.md 正文（含 frontmatter 之后的 body）
# 设计：构造含 frontmatter 的 SKILL.md，断言 read_body 返回正文
def test_read_body_returns_skill_md_content(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path, body="---\nname: foo\n---\n正文部分")
    reader = SkillContentReader()
    body = reader.read_body(skill_dir)
    assert "正文部分" in body


# 功能：read_body 在缺 SKILL.md 时抛 FileNotFoundError
# 设计：构造空 skill_dir，断言抛异常
def test_read_body_missing_skill_md_raises(tmp_path: Path) -> None:
    skill_dir = tmp_path / "empty_skill"
    skill_dir.mkdir()
    reader = SkillContentReader()
    with pytest.raises(FileNotFoundError):
        reader.read_body(skill_dir)


# 功能：read_body 在正文超过 max_bytes 时抛 ContentTooLargeError
# 设计：造 1KB body + max_bytes=10，断言抛 ContentTooLargeError
def test_read_body_oversize_raises(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path, body="A" * 1024)
    reader = SkillContentReader(max_bytes=10)
    with pytest.raises(ContentTooLargeError):
        reader.read_body(skill_dir)


# 功能：max_bytes 设为 None 时不限制大小
# 设计：造 1MB body + max_bytes=None，断言成功读出
def test_read_body_unlimited_when_none(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path, body="B" * (1024 * 1024))
    reader = SkillContentReader(max_bytes=None)
    body = reader.read_body(skill_dir)
    assert len(body) == 1024 * 1024


# 功能：read_body 返回字符串
# 设计：断言 type 是 str
def test_read_body_returns_str(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path, body="hello world")
    reader = SkillContentReader()
    body = reader.read_body(skill_dir)
    assert isinstance(body, str)


# ─────────────────────────── read_references ───────────────────────────


# 功能：read_references 按名读 references/<name>
# 设计：造 2 个 reference 文件，断言按名取到对应内容
def test_read_references_by_name(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(
        tmp_path,
        references={
            "alpha.md": "alpha content",
            "beta.md": "beta content",
        },
    )
    reader = SkillContentReader()
    assert reader.read_references(skill_dir, "alpha.md") == "alpha content"
    assert reader.read_references(skill_dir, "beta.md") == "beta content"


# 功能：read_references 支持子目录（references/prompts/query.md）
# 设计：造嵌套 references/prompts/query.md，断言可读
def test_read_references_nested_path(tmp_path: Path) -> None:
    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("body", encoding="utf-8")
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "prompts").mkdir()
    (skill_dir / "references" / "prompts" / "query.md").write_text("nested content", encoding="utf-8")

    reader = SkillContentReader()
    content = reader.read_references(skill_dir, "prompts/query.md")
    assert content == "nested content"


# 功能：read_references 在文件不存在时抛 FileNotFoundError
# 设计：references 目录存在但没目标文件
def test_read_references_missing_raises(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path)
    reader = SkillContentReader()
    with pytest.raises(FileNotFoundError):
        reader.read_references(skill_dir, "nonexistent.md")


# 功能：read_references 拒绝路径穿越（.. 段）
# 设计：尝试读 "../etc/passwd" 应被拒绝
def test_read_references_blocks_path_traversal(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path)
    reader = SkillContentReader()
    with pytest.raises(ValueError, match="path traversal"):
        reader.read_references(skill_dir, "../escape.md")


# 功能：read_references 单文件超 max_bytes 抛 ContentTooLargeError
# 设计：造 1KB reference + max_bytes=100
def test_read_references_oversize_raises(tmp_path: Path) -> None:
    skill_dir = _make_skill_dir(tmp_path, references={"big.md": "X" * 1024})
    reader = SkillContentReader(max_bytes=100)
    with pytest.raises(ContentTooLargeError):
        reader.read_references(skill_dir, "big.md")


# ─────────────────────────── 渐进式披露语义 ───────────────────────────


# 功能：构造 SkillContentReader 不读任何文件（不传 skill_dir）
# 设计：实例化不应触发任何 fs 操作；只检查构造不抛异常
def test_construction_does_not_read_files() -> None:
    reader = SkillContentReader()
    assert reader is not None
    assert reader.max_bytes == 64 * 1024  # 默认 64KB


# 功能：自定义 max_bytes 生效
# 设计：传 max_bytes=128，断言 reader.max_bytes == 128
def test_custom_max_bytes() -> None:
    reader = SkillContentReader(max_bytes=128)
    assert reader.max_bytes == 128


# 功能：默认 max_bytes = 64KB（契约 v1 自由调节）
# 设计：实例化默认 reader，断言 65536
def test_default_max_bytes_64k() -> None:
    reader = SkillContentReader()
    assert reader.max_bytes == 65536
