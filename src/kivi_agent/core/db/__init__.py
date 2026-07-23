"""Database Adapter 协议（agent: package-db-real-v4）。

统一查询接口：execute(sql, params) -> list[dict] + health_check() -> bool + close()。
3 种实现：Mock / SQLite / Postgres（Postgres 选作 E2E fallback）。

按 aigroup Wave 4 计划 §三 WT-F2：DatabaseAdapter Protocol + 3 Adapter + query_database 改 Adapter。
"""

from __future__ import annotations

from typing import Any, Protocol


class DatabaseAdapter(Protocol):
    """数据库适配器协议（agent: package-db-real-v4）。

    任何数据库后端（Mock / SQLite / Postgres）都实现这个协议，
    上层 query_database Tool 不感知具体实现。
    """

    async def execute(
        self,
        sql: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """执行 SQL，返回行列表（每行 dict 列名 -> 值）。"""
        ...

    async def health_check(self) -> bool:
        """健康检查：True=可连 / False=不可连（不抛错）。"""
        ...

    async def close(self) -> None:
        """关闭连接池。"""
        ...


# 对外暴露的符号（agent: package-db-real-v4）
__all__ = ["DatabaseAdapter"]
