from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from kivi_agent.core.memory.backend import MemoryAuditEvent, MemoryItem
from kivi_agent.core.memory.local_backend import LocalMemoryBackend

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_INDEX_FILE = "MEMORY.md"


@dataclass
class MemoryEntry:
    name: str
    type: str  # "user" | "feedback" | "project" | "reference"
    description: str
    body: str


class MemoryStore:
    # 初始化长期记忆存储根目录（典型路径 ~/.kivi/memory）
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


# ---- Wave 6.1 WT-J3：统一 Local / Vector 入口 ---------------------------------
# 设计：J1 会生产 `kivi_agent.core.memory.vector_backend.VectorMemoryBackend`，
#      本模块不能直接 import（v1 阶段 J1 尚未合并）。
#      这里用 Protocol 占位类型，让 `MemoryItemStore.set_vector()` 的类型签名
#      在 J1 集成时自动接受真正的 J1 类（结构子类型）。
#      集成期主控会确认 / 合并两边 Protocol，保持接口一致。
@runtime_checkable
class VectorMemoryBackend(Protocol):
    # 写入一条记忆，返回 memory id
    async def write(self, memory: MemoryItem) -> str: ...

    # 按 id 读取一条记忆
    async def read(self, memory_id: str) -> MemoryItem | None: ...

    # 按 query 检索 top_k 条记忆
    async def search(self, query: str, top_k: int = 5) -> list[MemoryItem]: ...

    # 按 id 更新一条记忆
    async def update(self, memory_id: str, memory: MemoryItem) -> None: ...

    # 按 id 删除一条记忆
    async def delete(self, memory_id: str) -> None: ...

    # 记录一次审计事件
    async def audit(self, event: MemoryAuditEvent) -> None: ...

    # 列出全部记忆（用于 dashboard GET /items；J1 ES 用 match_all 检索）
    async def list_all(self) -> list[MemoryItem]: ...


# 统一 Local / Vector 入口（Wave 6.1 WT-J3）。
# 设计：本地 backend 始终存在（默认 `~/.kivi/memory/`），vector 可选；
#      未配置 vector 时所有操作走 local；配置后 write/update/delete/audit 双写，
#      search 优先走 vector（语义召回更准），read/list/audit 走 local。
class MemoryItemStore:
    # 初始化 MemoryItemStore；vector 默认 None 表示仅本地
    def __init__(
        self,
        local: LocalMemoryBackend | None = None,
        vector: VectorMemoryBackend | None = None,
    ) -> None:
        self._local: LocalMemoryBackend = local or LocalMemoryBackend()
        self._vector: VectorMemoryBackend | None = vector

    # 取出 local backend（始终存在）
    def get_local(self) -> LocalMemoryBackend:
        return self._local

    # 取出 vector backend（可能为 None；为 None 表示未配置向量检索）
    def get_vector(self) -> VectorMemoryBackend | None:
        return self._vector

    # 注入 vector backend（J1 启动后由主控注入；测试可手动设置 mock）
    def set_vector(self, vector: VectorMemoryBackend) -> None:
        self._vector = vector

    # 列出全部记忆：vector 优先（一致性视图），否则 local
    async def list_all(self) -> list[MemoryItem]:
        if self._vector is not None:
            try:
                return await self._vector.list_all()
            except Exception:  # noqa: BLE001
                # vector 不可用时 fallback 到 local（与 Wave 6.1 §5 一致）
                pass
        return await self._local.list_all()

    # 检索：vector 优先，否则 local
    async def search(self, query: str, top_k: int = 5) -> list[MemoryItem]:
        if self._vector is not None:
            try:
                return await self._vector.search(query, top_k=top_k)
            except Exception:  # noqa: BLE001
                pass
        return await self._local.search(query, top_k=top_k)

    # 写入：local 总是写；vector 存在时双写
    async def write(self, memory: MemoryItem) -> str:
        mid = await self._local.write(memory)
        if self._vector is not None:
            try:
                await self._vector.write(memory)
            except Exception:  # noqa: BLE001
                # vector 写入失败不影响 local（fallback 语义）
                pass
        return mid

    # 读取：优先 local（与 dashboard 数据源一致）
    async def read(self, memory_id: str) -> MemoryItem | None:
        return await self._local.read(memory_id)

    # 更新：local 总是写；vector 存在时双写
    async def update(self, memory_id: str, memory: MemoryItem) -> None:
        await self._local.update(memory_id, memory)
        if self._vector is not None:
            try:
                await self._vector.update(memory_id, memory)
            except Exception:  # noqa: BLE001
                pass

    # 删除：local 总是写；vector 存在时双写
    async def delete(self, memory_id: str) -> None:
        await self._local.delete(memory_id)
        if self._vector is not None:
            try:
                await self._vector.delete(memory_id)
            except Exception:  # noqa: BLE001
                pass

    # 审计：只走 local（与 LocalMemoryBackend.audit 行为一致）
    async def audit(self, event: MemoryAuditEvent) -> None:
        await self._local.audit(event)


# ---- 单例管理（agent: package-dashboard-api-v61）-------------------------------
# 模式：与 Wave 5.1 / 5.2 dashboard 路由单例保持一致；
#       测试通过 `memory_dashboard._memory_store = MemoryItemStore(...)` 注入。
_memory_store: MemoryItemStore | None = None


# 获取 MemoryItemStore 单例
def get_memory_store() -> MemoryItemStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryItemStore()
    return _memory_store


# 重置单例（仅测试用）
def reset_memory_store_for_test() -> None:
    global _memory_store
    _memory_store = None


__all__ = [
    "MemoryEntry",
    "MemoryItemStore",
    "MemoryStore",
    "VectorMemoryBackend",
    "get_memory_store",
    "reset_memory_store_for_test",
]
