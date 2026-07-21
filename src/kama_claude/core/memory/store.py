from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_INDEX_FILE = "MEMORY.md"


@dataclass
class MemoryEntry:
    name: str
    type: str  # "user" | "feedback" | "project" | "reference"
    description: str
    body: str


class MemoryStore:
    # 初始化长期记忆存储根目录（典型路径 ~/.kama/memory）
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()
        self._root.mkdir(parents=True, exist_ok=True)

    # 把一条记忆以 <name>.md（YAML frontmatter + 正文）写入，同名文件直接覆盖
    def write(self, entry: MemoryEntry) -> Path:
        path = self._root / f"{entry.name}.md"
        content = (
            f"---\nname: {entry.name}\ntype: {entry.type}\ndescription: {entry.description}\n---\n\n"
            f"{entry.body}\n"
        )
        path.write_text(content, encoding="utf-8")
        self._refresh_index()
        return path

    # 遍历存储目录下所有 .md 文件，解析成 MemoryEntry 列表
    def list_all(self) -> list[MemoryEntry]:
        entries = []
        for path in sorted(self._root.glob("*.md")):
            if path.name == _INDEX_FILE:
                continue
            text = path.read_text(encoding="utf-8")
            match = _FRONTMATTER_RE.match(text)
            if not match:
                continue
            frontmatter, body = match.groups()
            fields: dict[str, str] = {}
            for line in frontmatter.splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    fields[key.strip()] = val.strip()
            entries.append(MemoryEntry(
                name=fields.get("name", path.stem),
                type=fields.get("type", "project"),
                description=fields.get("description", ""),
                body=body.strip(),
            ))
        return entries

    # 重建 MEMORY.md 索引（按 type 分组列出 name + description），便于人和工具快速浏览
    def _refresh_index(self) -> None:
        entries = self.list_all()
        by_type: dict[str, list[MemoryEntry]] = {}
        for entry in entries:
            by_type.setdefault(entry.type, []).append(entry)

        lines = ["# Long-term Memory Index", ""]
        for type_name, group in sorted(by_type.items()):
            lines.append(f"## {type_name}")
            for e in sorted(group, key=lambda x: x.name):
                lines.append(f"- **{e.name}** — {e.description}")
            lines.append("")
        (self._root / _INDEX_FILE).write_text("\n".join(lines), encoding="utf-8")
