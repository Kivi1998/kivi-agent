"""业务 Tool 的长期记忆后端（agent: package-c-v1）。

memory_save / memory_recall 两个业务 Tool 共用的本地文件存储。
与 core/memory/store.py 的 MemoryStore 区别：
- 支持 v1 长期记忆 4 字段：memory_type / importance / status / created_at
- 写入路径：~/.kivi/memory/（与 MemoryStore 同一目录，演示版兼容）
- 文件命名：<timestamp>_<id>.md（避免同名覆盖，按时间排序）
- recall 走简单 substring 匹配（演示版；真实走 embedding/ES 见 C 报告 §6.3）

不重写 MemoryStore：A 阶段冻结的 MemoryBackend Protocol + 现有 4 个测试
（test_memory_store / extractor / recall / loader）保持稳定。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# 长期记忆 frontmatter 字段（按 v1 + C 报告 §6.6 决议）
_FRONTMATTER_FIELDS: tuple[str, ...] = (
    "memory_id",
    "memory_type",
    "importance",
    "status",
    "created_at",
)


@dataclass
class LongTermMemoryEntry:
    """长期记忆条目（v1 字段集）。

    字段对齐 aigroup BaseMemoryStore + kivi-agent MemoryEntry：
    - memory_id：唯一 ID（演示版用 SHA256 前 12 位）
    - memory_type：fact / preference / decision / instruction / correction / summary / reference
    - importance：1-10（aigroup 范围）
    - status：active / pending / archived / expired
    - created_at：ISO 8601 UTC
    - content：正文（Markdown 格式）
    """

    memory_id: str
    memory_type: str
    importance: int
    status: str
    created_at: str
    content: str
    # 文件名（写入后填充，便于 recall 解析）
    filename: str = ""


# 简单 frontmatter 正则
_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


class LongTermMemoryBackend:
    """业务 Tool 用的长期记忆本地后端（agent: package-c-v1）。

    演示版：纯文件系统 + substring 匹配召回。
    未来切真 VectorMemoryBackend 时（C 报告 §6.3 ES 实现），
    本类可作为 LocalMemoryBackend 实现同样接口。
    """

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser()
        self._root.mkdir(parents=True, exist_ok=True)

    # 把一条记忆写入 <root>/<filename>.md（filename 由调用方决定或自动生成）
    def save(self, entry: LongTermMemoryEntry) -> Path:
        if not entry.filename:
            entry.filename = self._generate_filename(entry)
        path = self._root / entry.filename
        # frontmatter 4 字段
        frontmatter = (
            f"---\n"
            f"memory_id: {entry.memory_id}\n"
            f"memory_type: {entry.memory_type}\n"
            f"importance: {entry.importance}\n"
            f"status: {entry.status}\n"
            f"created_at: {entry.created_at}\n"
            f"---\n\n"
            f"{entry.content}\n"
        )
        path.write_text(frontmatter, encoding="utf-8")
        return path

    # 扫描全部 .md 文件，解析成 LongTermMemoryEntry 列表（按 created_at 倒序）
    def list_all(self) -> list[LongTermMemoryEntry]:
        entries: list[LongTermMemoryEntry] = []
        for path in sorted(self._root.glob("*.md"), reverse=True):
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
            try:
                entries.append(
                    LongTermMemoryEntry(
                        memory_id=fields.get("memory_id", path.stem),
                        memory_type=fields.get("memory_type", "reference"),
                        importance=int(fields.get("importance", "5")),
                        status=fields.get("status", "active"),
                        created_at=fields.get("created_at", ""),
                        content=body.strip(),
                        filename=path.name,
                    )
                )
            except (ValueError, KeyError):
                # 跳过格式不正确的文件
                continue
        # 按 created_at 倒序
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries

    # 简单 substring 召回：query 与 content 任意子串匹配 + 按 importance 排序
    def recall(self, query: str, top_k: int = 5) -> list[LongTermMemoryEntry]:
        all_entries = self.list_all()
        query_lower = query.lower().strip()
        if not query_lower:
            return all_entries[:top_k]
        # 简单 substring 匹配 + 评分（命中次数 × importance 权重）
        scored: list[tuple[float, LongTermMemoryEntry]] = []
        for entry in all_entries:
            content_lower = entry.content.lower()
            hit_count = content_lower.count(query_lower)
            if hit_count == 0:
                continue
            # 评分 = 命中次数 × importance（importance 越大权重越高）
            score = float(hit_count) * float(entry.importance)
            scored.append((score, entry))
        # 按 score 倒序
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    # 生成唯一文件名：<timestamp>_<id12>.md
    def _generate_filename(self, entry: LongTermMemoryEntry) -> str:
        # timestamp 文件名用 created_at 替换 : 和 . 为 _
        ts_safe = entry.created_at.replace(":", "").replace(".", "").replace("+", "p")
        return f"{ts_safe}_{entry.memory_id}.md"

    # 生成 memory_id：SHA256(content + memory_type + created_at)[:12]
    @staticmethod
    def make_memory_id(content: str, memory_type: str, created_at: str) -> str:
        h = hashlib.sha256()
        h.update(content.encode("utf-8"))
        h.update(b"|")
        h.update(memory_type.encode("utf-8"))
        h.update(b"|")
        h.update(created_at.encode("utf-8"))
        return h.hexdigest()[:12]

    # 标准化 created_at：UTC ISO 8601
    @staticmethod
    def now_iso() -> str:
        return datetime.now(UTC).isoformat()
