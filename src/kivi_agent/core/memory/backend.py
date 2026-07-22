from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


# 单条长期记忆条目（v1 §T3 + C §6.1 字段契约）
@dataclass
class MemoryItem:
    id: str
    content: str
    memory_type: str  # "user" | "feedback" | "project" | "reference" | ...
    importance: float
    status: str  # "active" | "pending" | "archived" | "expired"
    created_at: str  # ISO 8601
    expires_at: str | None = None  # None 表示永久


# 记忆审计事件（v1 §T3 + C §6.1 字段契约）
@dataclass
class MemoryAuditEvent:
    memory_id: str
    event_type: str  # "create" | "update" | "delete" | "read" | "expire"
    ts: str  # ISO 8601
    actor: str  # e.g. "user:u-1" / "system:extractor"


# 长期记忆后端接口契约（v1 §T3）
# 用 typing.Protocol 定义结构性子类型，C 阶段实现 VectorMemoryBackend 时直接满足本协议
# runtime_checkable 让 isinstance 校验可用（仅校验方法名存在，不校验签名）
@runtime_checkable
class MemoryBackend(Protocol):
    # 写入一条记忆，返回 memory id（调用方可立即拿到 id 用于回读）
    async def write(self, memory: MemoryItem) -> str: ...

    # 按 id 读取一条记忆；不存在返回 None
    async def read(self, memory_id: str) -> MemoryItem | None: ...

    # 按 query 检索 top_k 条记忆（向量召回/全文匹配由实现决定）
    async def search(self, query: str, top_k: int = 5) -> list[MemoryItem]: ...

    # 按 id 更新一条记忆的内容/字段
    async def update(self, memory_id: str, memory: MemoryItem) -> None: ...

    # 按 id 删除一条记忆
    async def delete(self, memory_id: str) -> None: ...

    # 记录一次审计事件（用于审计追踪与评测指标）
    async def audit(self, event: MemoryAuditEvent) -> None: ...
