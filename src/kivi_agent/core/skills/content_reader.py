"""Skills 2.0 渐进式披露：SkillContentReader。

启动时零文件 IO；调用 read_body / read_references 时按需读 SKILL.md 正文
和 references/ 子文件，避免大量 skill 启动时一次性加载所有正文。

大小限制默认 64KB，配置可调（None 表示无限制）。路径穿越（.. 段 / 绝对路径）
会被拒绝，避免 references 越权读到 skill_dir 之外的文件。
"""
from __future__ import annotations

from pathlib import Path

# 默认正文 / reference 大小上限：64KB（与 aigroup SKILL_SCRIPT_MAX_OUTPUT_BYTES 解耦，
# 此处管"输入正文大小"，那里管"脚本输出大小"）
DEFAULT_MAX_BYTES = 64 * 1024  # 64KB


class ContentTooLargeError(Exception):
    """Skill 正文 / reference 超过 max_bytes 限制。"""


# Skill 正文 + reference 懒加载器（启动时零文件 IO，调用时按需读）
class SkillContentReader:
    def __init__(self, max_bytes: int | None = DEFAULT_MAX_BYTES) -> None:
        self.max_bytes = max_bytes

    # 读 SKILL.md 正文（完整 markdown，含 frontmatter）
    def read_body(self, skill_dir: Path) -> str:
        path = skill_dir / "SKILL.md"
        if not path.exists():
            raise FileNotFoundError(f"SKILL.md not found in {skill_dir}")
        text = path.read_text(encoding="utf-8")
        self._enforce_size(text, source=f"body of {path}")
        return text

    # 读 references/<name>（支持子目录如 prompts/query.md）
    def read_references(self, skill_dir: Path, name: str) -> str:
        self._check_path_traversal(name)
        path = (skill_dir / "references" / name).resolve()
        # 解析后再次校验仍在 references/ 之下
        try:
            path.relative_to((skill_dir / "references").resolve())
        except ValueError as e:
            raise ValueError(f"path traversal blocked: {name}") from e
        if not path.exists():
            raise FileNotFoundError(f"reference not found: {name}")
        text = path.read_text(encoding="utf-8")
        self._enforce_size(text, source=f"reference {name}")
        return text

    # 拒路径穿越（`..` 段或绝对路径）
    def _check_path_traversal(self, name: str) -> None:
        if ".." in Path(name).parts or Path(name).is_absolute():
            raise ValueError(f"path traversal blocked: {name}")

    # 校验文本大小（None 表示不限制）
    def _enforce_size(self, text: str, *, source: str) -> None:
        if self.max_bytes is None:
            return
        size = len(text.encode("utf-8"))
        if size > self.max_bytes:
            raise ContentTooLargeError(
                f"content too large; {source} bytes {size}, limit {self.max_bytes}"
            )
