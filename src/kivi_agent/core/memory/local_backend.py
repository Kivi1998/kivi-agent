from __future__ import annotations

import re
from pathlib import Path

from kivi_agent.core.memory.backend import MemoryAuditEvent, MemoryBackend, MemoryItem


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_AUDIT_LOG = "audit.log"


# 本地 Markdown 文件后端：把 MemoryItem 持久化到 <root>/<id>.md（YAML frontmatter + 正文）
# frontmatter 包含 v1 §T4 + C §6.2 4 字段：memory_type / importance / status / expires_at
# expires_at=None 时写入 "never" 字符串，保持可读性（C §6.6 永久记忆约定）
class LocalMemoryBackend:
    # 初始化本地记忆后端；root 默认 ~/.kivi/memory/（工程已重命名）
    def __init__(self, root: Path | None = None) -> None:
        self.root: Path = (root or Path("~/.kivi/memory")).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)

    # 把 MemoryItem 序列化为 <id>.md；id 即返回的 memory_id
    async def write(self, memory: MemoryItem) -> str:
        path = self.root / f"{memory.id}.md"
        content = self._render(memory)
        path.write_text(content, encoding="utf-8")
        return memory.id

    # 按 id 读取记忆；不存在返回 None
    async def read(self, memory_id: str) -> MemoryItem | None:
        path = self.root / f"{memory_id}.md"
        if not path.exists():
            return None
        return self._parse(path)

    # 按 query 在 content 中做子串匹配（Markdown 全文搜索作为向量召回的占位实现）
    # 空 query 返回空列表，避免把所有记忆返回
    async def search(self, query: str, top_k: int = 5) -> list[MemoryItem]:
        if not query:
            return []
        results: list[MemoryItem] = []
        for path in sorted(self.root.glob("*.md")):
            item = self._parse(path)
            if item is None:
                continue
            if query in item.content:
                results.append(item)
            if len(results) >= top_k:
                break
        return results

    # 按 id 覆盖写入；id 不变
    async def update(self, memory_id: str, memory: MemoryItem) -> None:
        await self.write(memory)

    # 按 id 删除文件；id 不存在时为幂等操作
    async def delete(self, memory_id: str) -> None:
        path = self.root / f"{memory_id}.md"
        if path.exists():
            path.unlink()

    # 把审计事件追加到 audit.log（NDJSON 风格的事件溯源基础）
    async def audit(self, event: MemoryAuditEvent) -> None:
        log = self.root / _AUDIT_LOG
        line = (
            f"{event.ts} {event.event_type} {event.memory_id} actor={event.actor}\n"
        )
        with log.open("a", encoding="utf-8") as f:
            f.write(line)

    # 渲染单个 MemoryItem 为带 frontmatter 的 markdown
    def _render(self, m: MemoryItem) -> str:
        expires = m.expires_at if m.expires_at is not None else "never"
        return (
            "---\n"
            f"id: {m.id}\n"
            f"memory_type: {m.memory_type}\n"
            f"importance: {m.importance}\n"
            f"status: {m.status}\n"
            f"created_at: {m.created_at}\n"
            f"expires_at: {expires}\n"
            "---\n\n"
            f"{m.content}\n"
        )

    # 从 markdown 文件解析为 MemoryItem；frontmatter 不匹配返回 None
    def _parse(self, path: Path) -> MemoryItem | None:
        text = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(text)
        if not match:
            return None
        frontmatter, body = match.groups()
        fields: dict[str, str] = {}
        for line in frontmatter.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                fields[key.strip()] = val.strip()
        expires_raw = fields.get("expires_at", "never")
        expires_val: str | None = None if expires_raw == "never" else expires_raw
        return MemoryItem(
            id=fields.get("id", path.stem),
            content=body.strip(),
            memory_type=fields.get("memory_type", "user"),
            importance=float(fields.get("importance", "0.5")),
            status=fields.get("status", "active"),
            created_at=fields.get("created_at", ""),
            expires_at=expires_val,
        )
