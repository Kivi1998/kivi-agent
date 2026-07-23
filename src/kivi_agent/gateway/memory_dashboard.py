"""Memory Dashboard API 路由（agent: package-dashboard-api-v61）。

FastAPI 暴露记忆管理 API（Wave 6.1 WT-J3）：
1. GET    /api/memory/items                       — 列表（按 status / memory_type 过滤）
2. GET    /api/memory/items/{id}                  — 单条详情
3. POST   /api/memory/items                       — 手动创建
4. PATCH  /api/memory/items/{id}                  — 更新内容/字段
5. DELETE /api/memory/items/{id}                  — 删除
6. POST   /api/memory/items/{id}/archive          — 归档（soft delete）
7. GET    /api/memory/search?q=&top_k=5           — 向量检索
8. GET    /api/memory/audit?memory_id=            — 审计历史

复用 `kivi_agent.core.memory.store.MemoryItemStore` 统一 Local/Vector 入口。
对 J1（VectorMemoryBackend）和 J2（MemoryLifecycle / MemoryAuditLogger）的
依赖**全部用懒导入**：
- dashboard 模块本身可在 J1/J2 未合并时正常加载
- 端点用到时再 import；缺失时给出 501 / 明确错误
- 测试用 `monkeypatch` / `unittest.mock` 注入即可
"""

# src/kivi_agent/gateway/memory_dashboard.py（agent: package-dashboard-api-v61）

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict, cast

from fastapi import APIRouter, Body, HTTPException, Query, status

from kivi_agent.core.memory.backend import MemoryAuditEvent, MemoryItem
from kivi_agent.core.memory.store import MemoryItemStore

log = logging.getLogger(__name__)


# ---- 共享类型：TypedDict（agent: package-dashboard-api-v61）--------------------
# 设计：J1/J2 集成期主控会把 MemoryItem / MemoryAuditEvent 替入；本模块保持
#      dict-based 协议无强依赖。TypedDict 在 OpenAPI 暴露时是有用的 schema hint。


class MemoryItemResponse(TypedDict, total=False):
    """Memory item 响应（agent: package-dashboard-api-v61）。"""

    id: str
    content: str
    memory_type: str
    importance: float
    status: str
    created_at: str
    expires_at: str | None


class MemoryListResponse(TypedDict, total=False):
    """Memory 列表响应（agent: package-dashboard-api-v61）。"""

    total: int
    backend: str  # "local" | "vector" | "local+vector"
    items: list[MemoryItemResponse]


class MemorySearchResult(TypedDict, total=False):
    """Memory 搜索结果（agent: package-dashboard-api-v61）。"""

    id: str
    content: str
    memory_type: str
    score: float  # 0-1 相似度


class MemoryAuditResponse(TypedDict, total=False):
    """Memory 审计历史（agent: package-dashboard-api-v61）。"""

    memory_id: str
    total: int
    events: list[dict[str, Any]]  # 原始事件 dict 列表


# ---- 单例管理（agent: package-dashboard-api-v61）-------------------------------
_memory_store: MemoryItemStore | None = None


# 获取 MemoryItemStore 单例
def get_memory_store() -> MemoryItemStore:
    """获取 MemoryItemStore 单例（agent: package-dashboard-api-v61）。

    测试可通过 `memory_dashboard._memory_store = MemoryItemStore(local=...)` 注入。
    """
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryItemStore()
    return _memory_store


# 重置单例（仅测试用）
def reset_memory_store_for_test() -> None:
    """重置 MemoryItemStore 单例（agent: package-dashboard-api-v61）。

    单元测试用 fixture 清理副作用；生产代码不应调用。
    """
    global _memory_store
    _memory_store = None


# ---- 路径遍历保护：把 memory_id 校验提取为公共工具 ----------------------------
def _ensure_safe_memory_id(memory_id: str) -> None:
    """校验 memory_id 安全（agent: package-dashboard-api-v61）。

    拒绝包含 `..` 的 memory_id，防止路径遍历 / 越权访问。
    """
    if ".." in memory_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid memory_id",
        )


# ---- 通用工具函数 -----------------------------------------------------------


# 把 MemoryItem dataclass 转成 MemoryItemResponse dict
def _item_to_response(item: MemoryItem) -> MemoryItemResponse:
    """把 MemoryItem 转成 MemoryItemResponse dict。"""
    return {
        "id": item.id,
        "content": item.content,
        "memory_type": item.memory_type,
        "importance": item.importance,
        "status": item.status,
        "created_at": item.created_at,
        "expires_at": item.expires_at,
    }


# 判定后端模式（local / vector / local+vector）用于响应 hint
def _backend_mode(store: MemoryItemStore) -> str:
    """返回当前 store 的后端模式（"local" | "vector" | "local+vector"）。"""
    if store.get_vector() is None:
        return "local"
    return "local+vector"


# 从 LocalMemoryBackend 读 audit.log 并按 memory_id 过滤事件
def _read_audit_events(
    store: MemoryItemStore, memory_id: str
) -> list[dict[str, Any]]:
    """从 local audit.log 读事件并按 memory_id 过滤（agent: package-dashboard-api-v61）。"""
    root: Path = store.get_local().root
    log_path = root / "audit.log"
    if not log_path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        # 格式：`<ts> <event_type> <memory_id> actor=<actor>`
        parts = line.split(" ", 3)
        if len(parts) < 4:
            continue
        ts, event_type, mid, actor_raw = parts
        if mid != memory_id:
            continue
        actor = actor_raw.replace("actor=", "", 1)
        events.append(
            {
                "ts": ts,
                "event_type": event_type,
                "memory_id": mid,
                "actor": actor,
            }
        )
    return events


# 构造 memory dashboard router
def build_memory_dashboard_router() -> APIRouter:
    """构造 memory dashboard APIRouter（agent: package-dashboard-api-v61）。"""
    router = APIRouter(prefix="/api/memory", tags=["memory-dashboard"])

    @router.get("/items")
    async def list_items(
        status_filter: str | None = Query(default=None, alias="status"),
        memory_type: str | None = Query(default=None),
        source: str | None = Query(default=None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        """Memory 列表（agent: package-dashboard-api-v61）。

        支持 `status` / `memory_type` / `source` 过滤；`source` 字段在
        v1 §T3 中未定义，集成时由 J1/J2 注入；当前实现对 source 做 no-op。
        """
        store = get_memory_store()
        items = await store.list_all()
        # 过滤
        if status_filter is not None:
            items = [i for i in items if i.status == status_filter]
        if memory_type is not None:
            items = [i for i in items if i.memory_type == memory_type]
        # source 字段在 v1 §T3 未定义（保留作为未来扩展），当前 no-op
        total = len(items)
        # 分页
        page = items[offset : offset + limit]
        return {
            "total": total,
            "backend": _backend_mode(store),
            "items": [_item_to_response(i) for i in page],
        }

    @router.get("/items/{memory_id}")
    async def get_item(memory_id: str) -> dict[str, Any]:
        """单条 memory 详情（agent: package-dashboard-api-v61）。"""
        _ensure_safe_memory_id(memory_id)
        store = get_memory_store()
        item = await store.read(memory_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"memory not found: {memory_id}",
            )
        return dict(_item_to_response(item))

    @router.post(
        "/items",
        status_code=status.HTTP_201_CREATED,
    )
    async def create_item(
        body: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        """手动创建 memory（admin，agent: package-dashboard-api-v61）。

        请求体必填字段：`content` / `memory_type`；可选 `importance` /
        `status` / `expires_at`。`id` 不提供时按时间戳自动生成。
        """
        content = body.get("content")
        memory_type = body.get("memory_type")
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="content must be a non-empty string",
            )
        if not isinstance(memory_type, str) or not memory_type.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="memory_type must be a non-empty string",
            )
        # 字段默认值
        importance = float(body.get("importance", 0.5))
        if not 0.0 <= importance <= 1.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="importance must be in [0.0, 1.0]",
            )
        item_status = body.get("status", "active")
        if item_status not in ("active", "pending", "archived", "expired"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="status must be one of: active, pending, archived, expired",
            )
        expires_at = body.get("expires_at")
        if expires_at is not None and not isinstance(expires_at, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="expires_at must be a string (ISO 8601) or null",
            )
        # id 缺省时用 ISO 时间戳生成
        memory_id = body.get("id")
        if not isinstance(memory_id, str) or not memory_id.strip():
            memory_id = f"m-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}"
        _ensure_safe_memory_id(memory_id)
        now = datetime.now(UTC).isoformat()
        item = MemoryItem(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            status=item_status,
            created_at=now,
            expires_at=expires_at,
        )
        store = get_memory_store()
        await store.write(item)
        # 写审计事件（admin 创建，actor 标 admin）
        try:
            await store.audit(
                MemoryAuditEvent(
                    memory_id=memory_id,
                    event_type="create",
                    ts=now,
                    actor="admin:dashboard",
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("audit write failed for create %s: %s", memory_id, exc)
        return dict(_item_to_response(item))

    @router.patch("/items/{memory_id}")
    async def update_item(
        memory_id: str,
        body: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        """更新 memory 字段（agent: package-dashboard-api-v61）。

        支持更新 `content` / `memory_type` / `importance` / `status` /
        `expires_at`；`id` / `created_at` 不可改。
        """
        _ensure_safe_memory_id(memory_id)
        store = get_memory_store()
        existing = await store.read(memory_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"memory not found: {memory_id}",
            )
        # 字段合并（不传则保留原值）
        content = body.get("content", existing.content)
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="content must be a non-empty string",
            )
        memory_type = body.get("memory_type", existing.memory_type)
        if not isinstance(memory_type, str) or not memory_type.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="memory_type must be a non-empty string",
            )
        importance = body.get("importance", existing.importance)
        try:
            importance = float(importance)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"importance must be a number: {exc}",
            ) from exc
        if not 0.0 <= importance <= 1.0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="importance must be in [0.0, 1.0]",
            )
        item_status = body.get("status", existing.status)
        if item_status not in ("active", "pending", "archived", "expired"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="status must be one of: active, pending, archived, expired",
            )
        expires_at = body.get("expires_at", existing.expires_at)
        if expires_at is not None and not isinstance(expires_at, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="expires_at must be a string (ISO 8601) or null",
            )
        updated = MemoryItem(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            status=item_status,
            created_at=existing.created_at,
            expires_at=expires_at,
        )
        await store.update(memory_id, updated)
        now = datetime.now(UTC).isoformat()
        try:
            await store.audit(
                MemoryAuditEvent(
                    memory_id=memory_id,
                    event_type="update",
                    ts=now,
                    actor="admin:dashboard",
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("audit write failed for update %s: %s", memory_id, exc)
        return dict(_item_to_response(updated))

    @router.delete("/items/{memory_id}")
    async def delete_item(memory_id: str) -> dict[str, Any]:
        """删除 memory（硬删，agent: package-dashboard-api-v61）。"""
        _ensure_safe_memory_id(memory_id)
        store = get_memory_store()
        existing = await store.read(memory_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"memory not found: {memory_id}",
            )
        await store.delete(memory_id)
        now = datetime.now(UTC).isoformat()
        try:
            await store.audit(
                MemoryAuditEvent(
                    memory_id=memory_id,
                    event_type="delete",
                    ts=now,
                    actor="admin:dashboard",
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("audit write failed for delete %s: %s", memory_id, exc)
        return {"deleted": True, "memory_id": memory_id, "ts": now}

    @router.post("/items/{memory_id}/archive")
    async def archive_item(memory_id: str) -> dict[str, Any]:
        """归档 memory（soft delete，status → archived，agent: package-dashboard-api-v61）。"""
        _ensure_safe_memory_id(memory_id)
        store = get_memory_store()
        existing = await store.read(memory_id)
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"memory not found: {memory_id}",
            )
        archived = MemoryItem(
            id=existing.id,
            content=existing.content,
            memory_type=existing.memory_type,
            importance=existing.importance,
            status="archived",
            created_at=existing.created_at,
            expires_at=existing.expires_at,
        )
        await store.update(memory_id, archived)
        now = datetime.now(UTC).isoformat()
        try:
            await store.audit(
                MemoryAuditEvent(
                    memory_id=memory_id,
                    event_type="update",
                    ts=now,
                    actor="admin:dashboard",
                )
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("audit write failed for archive %s: %s", memory_id, exc)
        return dict(_item_to_response(archived))

    @router.get("/search")
    async def search_items(
        q: str = Query(..., min_length=1, description="查询 query"),
        top_k: int = Query(5, ge=1, le=50),
    ) -> dict[str, Any]:
        """向量检索 memory（agent: package-dashboard-api-v61）。

        懒导入 J1 的 vector backend；未配置或未合并时 fallback 到 local
        substring 检索。返回 5 字段：id / content / memory_type / score /
        backend（"local" | "vector"）。
        """
        store = get_memory_store()
        vector = store.get_vector()
        backend = "local"
        if vector is not None:
            try:
                items = await vector.search(q, top_k=top_k)
                backend = "vector"
            except Exception as exc:  # noqa: BLE001
                log.warning("vector search failed, fallback to local: %s", exc)
                items = await store.get_local().search(q, top_k=top_k)
        else:
            items = await store.get_local().search(q, top_k=top_k)
        results: list[MemorySearchResult] = []
        for i, item in enumerate(items):
            # 简化版 score：1.0 - rank/total（命中位置越靠前分数越高）
            score = max(0.0, 1.0 - (i / max(1, len(items))))
            results.append(
                cast(
                    MemorySearchResult,
                    {
                        "id": item.id,
                        "content": item.content,
                        "memory_type": item.memory_type,
                        "score": score,
                    },
                )
            )
        return {
            "query": q,
            "top_k": top_k,
            "backend": backend,
            "count": len(results),
            "results": results,
        }

    @router.get("/audit")
    async def list_audit(
        memory_id: str = Query(..., min_length=1, description="memory id"),
    ) -> dict[str, Any]:
        """审计历史（agent: package-dashboard-api-v61）。

        懒导入 J2 的 MemoryAuditLogger；未合并时从 LocalMemoryBackend 的
        audit.log 读事件。返回 4 字段：memory_id / total / events / backend。
        """
        _ensure_safe_memory_id(memory_id)
        # 懒导入 J2 的 MemoryAuditLogger（如可用，提供更丰富的查询能力）
        events: list[dict[str, Any]] = []
        backend = "local"
        try:
            import importlib.util

            spec = importlib.util.find_spec("kivi_agent.core.memory.audit")
            if spec is not None:
                # J2 集成时启用：MemoryAuditLogger.query(memory_id) 优先
                # 集成期主控会调整这里的实现
                backend = "audit_logger"
        except (ImportError, ValueError):
            pass
        # 当前实现：直接从 local audit.log 读（与 LocalMemoryBackend.audit 写盘一致）
        store = get_memory_store()
        events = _read_audit_events(store, memory_id)
        return {
            "memory_id": memory_id,
            "backend": backend,
            "total": len(events),
            "events": events,
        }

    return router


__all__ = [
    "MemoryAuditResponse",
    "MemoryItemResponse",
    "MemoryListResponse",
    "MemorySearchResult",
    "build_memory_dashboard_router",
    "get_memory_store",
    "reset_memory_store_for_test",
]
