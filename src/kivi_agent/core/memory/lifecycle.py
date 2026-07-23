"""记忆生命周期编排（Wave 6.1 J2 增强）。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, TypedDict

from kivi_agent.core.memory.audit import MemoryAuditLogger
from kivi_agent.core.memory.backend import MemoryAuditEvent, MemoryItem
from kivi_agent.core.memory.dedup import EmbeddingFn, SemanticDeduplicator
from kivi_agent.core.memory.expire import MemoryExpiryPolicy
from kivi_agent.core.memory.filter import SensitiveInfoFilter

if TYPE_CHECKING:
    from kivi_agent.core.memory.backend import MemoryBackend


# 生命周期处理结果。
class ProcessResult(TypedDict):
    action: str  # "added" | "merged" | "skipped" | "failed"
    memory_id: str  # 新记忆的 id（无论 action 如何）
    warnings: list[str]  # 过滤/去重/过期等阶段的告警


# lifecycle 不暴露 "skipped"——若 dedup 返回 skip，lifecycle 仍视作不写。
# 但 ProcessResult 包含 "skipped" 字段以保持与 plan 字段名一致；运行时不会返回。
# 这里我们用 dict 形式实现，调用方可自由访问。

EmbeddingProvider = EmbeddingFn  # 向后兼容别名


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class MemoryLifecycle:
    """记忆生命周期编排：filter → dedup → write → audit → expire。"""

    def __init__(
        self,
        filter: SensitiveInfoFilter | None = None,
        deduplicator: SemanticDeduplicator | None = None,
        expiry_policy: MemoryExpiryPolicy | None = None,
        embedding_fn: EmbeddingFn | None = None,
        dedup_threshold: float = 0.95,
    ) -> None:
        self._filter = filter or SensitiveInfoFilter()
        # dedup 优先用注入的 SemanticDeduplicator；否则若给了 embedding_fn 就现造
        dedup: SemanticDeduplicator | None
        if deduplicator is not None:
            dedup = deduplicator
        elif embedding_fn is not None:
            dedup = SemanticDeduplicator(
                embedding_fn=embedding_fn, threshold=dedup_threshold
            )
        else:
            dedup = None
        self._dedup = dedup
        self._expiry = expiry_policy or MemoryExpiryPolicy()

    @property
    def filter(self) -> SensitiveInfoFilter:
        return self._filter

    @property
    def deduplicator(self) -> SemanticDeduplicator | None:
        return self._dedup

    @property
    def expiry(self) -> MemoryExpiryPolicy:
        return self._expiry

    # 处理新记忆：先过滤敏感信息，再去重，再写，最后审计。任一步骤异常降级。
    async def process(
        self,
        new_memory: MemoryItem,
        backend: MemoryBackend,
        audit_logger: MemoryAuditLogger,
    ) -> ProcessResult:
        warnings: list[str] = []

        # 1) filter：替换 content 为 sanitized 版本
        filtered = self._filter.filter(new_memory.content)
        warnings.extend(filtered["warnings"])
        sanitized_content = filtered["sanitized"]
        processed = replace(new_memory, content=sanitized_content)

        # 2) dedup：与 backend 已有记忆对比（仅 active/pending）
        if self._dedup is not None:
            try:
                existing = await self._list_existing(backend)
            except Exception:
                # 拉取失败 → 跳过 dedup，按新增处理
                existing = []
                warnings.append("dedup: list_existing failed")
            try:
                dedup_result = self._dedup.deduplicate(processed, existing)
            except Exception as exc:
                warnings.append(f"dedup: error {exc}")
                dedup_result = {
                    "action": "add",
                    "merged_with": None,
                    "score": 0.0,
                    "reason": "error",
                }
            if dedup_result["action"] == "merge" and dedup_result["merged_with"]:
                # 合并：更新被合并的条目（保留较新 content），审计 merge 事件
                target_id = dedup_result["merged_with"]
                target = await backend.read(target_id)
                if target is not None:
                    merged = replace(
                        target,
                        content=sanitized_content,
                        importance=max(target.importance, processed.importance),
                    )
                    await backend.update(target_id, merged)
                await audit_logger.record(MemoryAuditEvent(
                    memory_id=processed.id,
                    event_type="update",
                    ts=_now_iso(),
                    actor="system:lifecycle:merge",
                ))
                return ProcessResult(
                    action="merged",
                    memory_id=target_id,
                    warnings=warnings,
                )

        # 3) write：写入 backend
        try:
            await backend.write(processed)
        except Exception as exc:
            warnings.append(f"write: error {exc}")
            return ProcessResult(
                action="failed",
                memory_id=processed.id,
                warnings=warnings,
            )

        # 4) audit
        try:
            await audit_logger.record(MemoryAuditEvent(
                memory_id=processed.id,
                event_type="create",
                ts=_now_iso(),
                actor="system:lifecycle",
            ))
        except Exception as exc:
            warnings.append(f"audit: error {exc}")

        return ProcessResult(
            action="added",
            memory_id=processed.id,
            warnings=warnings,
        )

    # 拉取 backend 现有活跃记忆（用于去重对比）
    async def _list_existing(
        self, backend: MemoryBackend
    ) -> list[MemoryItem]:
        list_all = getattr(backend, "list_all", None)
        if callable(list_all):
            res = list_all()
            if hasattr(res, "__await__"):
                return list(await res)
            return list(res)
        # 兜底：用 search 拉全量
        return list(await backend.search("*", top_k=10000))


# 便捷工厂：构造最常用配置
def build_default_lifecycle(
    embedding_fn: EmbeddingFn | None = None,
    filter: SensitiveInfoFilter | None = None,
) -> MemoryLifecycle:
    """构造默认 lifecycle：带过滤 + 去重（若有 embedding_fn）+ 过期。"""
    return MemoryLifecycle(
        filter=filter or SensitiveInfoFilter(),
        embedding_fn=embedding_fn,
    )
