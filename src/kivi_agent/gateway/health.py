"""详细健康检查端点（agent: package-config-v4）。

GET /health/detailed 返回每个 Adapter 的健康状态：

    {
      "status": "healthy" | "degraded",
      "services": {
        "rag": {"mode": "http" | "mock", "healthy": bool, "url": "..." | null},
        "db":  {"mode": "real" | "mock", "healthy": bool, "url": "..." | null}
      }
    }

HTTP 状态码：
- 200 — 所有 Adapter 健康
- 207 — 任一 Adapter 不健康（Multi-Status，degraded 但仍可用）

设计说明：
- 参数采用结构化类型（Protocol）：任何具有 `async health_check() -> bool`
  的对象都可传入；不强依赖具体 RagKbClient / DatabaseAdapter 类
  （它们由其他 WT 负责实现），便于主 agent 集成时直接复用
- URL 字段从对象的常见属性（_base_url / api_url / _db_path / _dsn 等）抽取
- Mock 模式（client/adapter=None）视作永远健康
"""

from __future__ import annotations

from typing import Any, Protocol

from fastapi import APIRouter
from fastapi.responses import JSONResponse


class _HealthCheckable(Protocol):
    """任何具有 `async health_check() -> bool` 方法的对象（agent: package-config-v4）。"""

    async def health_check(self) -> bool: ...


# 从对象中提取连接 URL/路径（agent: package-config-v4）
def _extract_url(obj: Any) -> str | None:
    """从 client/adapter 抽取 URL/路径字段，便于诊断（agent: package-config-v4）。

    按 RAG → DB 常见命名顺序回退；找不到返回 None。
    """
    for attr in ("_base_url", "api_url", "base_url"):
        val = getattr(obj, attr, None)
        if isinstance(val, str):
            return val
    for attr in ("_db_path", "_dsn", "database_url", "dsn", "path"):
        val = getattr(obj, attr, None)
        if isinstance(val, str):
            return val
    return None


# 构造 health router（agent: package-config-v4）
def build_health_router(
    rag_client: _HealthCheckable | None,
    db_adapter: _HealthCheckable | None,
) -> APIRouter:
    """构造 health router（agent: package-config-v4）。

    参数：
    - `rag_client`: 真实 RAG 客户端（mock 模式传 None）
    - `db_adapter`: 真实 DB Adapter（mock 模式传 None）
    """
    router = APIRouter()

    @router.get("/health/detailed")
    async def health_detailed() -> JSONResponse:
        """GET /health/detailed（agent: package-config-v4）。"""
        rag_status: dict[str, Any] = {"mode": "mock", "healthy": True, "url": None}
        if rag_client is not None:
            rag_status = {
                "mode": "http",
                "healthy": await rag_client.health_check(),
                "url": _extract_url(rag_client),
            }
        db_status: dict[str, Any] = {"mode": "mock", "healthy": True, "url": None}
        if db_adapter is not None:
            db_status = {
                "mode": "real",
                "healthy": await db_adapter.health_check(),
                "url": _extract_url(db_adapter),
            }
        all_healthy = bool(rag_status["healthy"]) and bool(db_status["healthy"])
        return JSONResponse(
            status_code=200 if all_healthy else 207,
            content={
                "status": "healthy" if all_healthy else "degraded",
                "services": {"rag": rag_status, "db": db_status},
            },
        )

    return router


__all__ = ["build_health_router"]
