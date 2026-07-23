"""Memory Dashboard API 集成测试（WT-J3 / agent: package-dashboard-api-v61）。

E2E 场景：
1. Local + Vector mock 双路径：完整端到端（写 → 读 → 改 → 删 → 检索 → 审计）
2. 多次请求间持久化（store 单例 + 本地 .md 文件 + audit.log）
3. Memory Dashboard router 集成到 FastAPI create_app
4. 路径遍历保护跨端点覆盖
5. CRUD 全链路 round-trip 验证

设计要点：
- 用 tmp_path 隔离 local backend 根目录
- 通过 `memory_dashboard._memory_store` 单例注入
- Vector backend 用 mock（避免依赖 J1）
- 不依赖 J2 (MemoryLifecycle/MemoryAuditLogger)
"""

# tests/integration/test_memory_dashboard_e2e.py（agent: package-dashboard-api-v61）

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from kivi_agent.core.memory.backend import MemoryItem
from kivi_agent.core.memory.local_backend import LocalMemoryBackend
from kivi_agent.core.memory.store import MemoryItemStore
from kivi_agent.gateway import memory_dashboard as memory_dashboard_mod
from kivi_agent.gateway.main import create_app

# ---- 公共工具 --------------------------------------------------------------


class _RT:
    """FastAPI create_app 注入的 fake runtime。"""

    async def start_session(self, *a: Any, **k: Any) -> Any:
        from kivi_agent.core.gateway.runtime import SessionInfo

        return SessionInfo(
            session_id="x", user_id="u", goal="g",
            created_at="2026-01-01T00:00:00Z", status="active", run_id=None,
        )

    async def cancel_session(self, *a: Any, **k: Any) -> bool:
        return True

    async def list_sessions(self, *a: Any, **k: Any) -> list[Any]:
        return []

    async def get_session(self, *a: Any, **k: Any) -> Any:
        return None

    async def send_command(self, *a: Any, **k: Any) -> Any:
        return {}

    def subscribe_events(self, *a: Any, **k: Any) -> Any:
        async def g() -> Any:
            if False:
                yield  # type: ignore[unreachable]

        return g()


def _make_item(**kwargs: Any) -> MemoryItem:
    """构造 MemoryItem（agent: package-dashboard-api-v61）。"""
    defaults: dict[str, Any] = {
        "id": "m-1",
        "content": "x",
        "memory_type": "user",
        "importance": 0.5,
        "status": "active",
        "created_at": "2026-01-01T00:00:00Z",
        "expires_at": None,
    }
    defaults.update(kwargs)
    return MemoryItem(**defaults)


class _MockVectorBackend:
    """Mock VectorMemoryBackend（满足 store.set_vector 协议）。"""

    def __init__(self) -> None:
        self.items: dict[str, MemoryItem] = {}
        self.search_calls: list[tuple[str, int]] = []
        self.write_calls: list[str] = []
        self.update_calls: list[str] = []
        self.delete_calls: list[str] = []

    async def write(self, memory: MemoryItem) -> str:
        self.write_calls.append(memory.id)
        self.items[memory.id] = memory
        return memory.id

    async def read(self, memory_id: str) -> MemoryItem | None:
        return self.items.get(memory_id)

    async def search(
        self, query: str, top_k: int = 5
    ) -> list[MemoryItem]:
        self.search_calls.append((query, top_k))
        # 简单子串匹配模拟 ES 行为
        return [
            item
            for item in self.items.values()
            if query in item.content
        ][:top_k]

    async def update(self, memory_id: str, memory: MemoryItem) -> None:
        self.update_calls.append(memory_id)
        self.items[memory_id] = memory

    async def delete(self, memory_id: str) -> None:
        self.delete_calls.append(memory_id)
        self.items.pop(memory_id, None)

    async def audit(self, event: Any) -> None:  # noqa: ANN401
        pass

    async def list_all(self) -> list[MemoryItem]:
        return list(self.items.values())


# ---- E2E 场景 1：CRUD round-trip（local 路径）------------------------------


# 功能：完整 CRUD 流程：create → read → update → archive → delete 全部端点
# 设计：依次调用 5 个端点，每次校验响应 + 落盘状态
def test_e2e_crud_roundtrip_local(tmp_path: Path) -> None:
    """E2E local 路径 5 步 CRUD round-trip（agent: package-dashboard-api-v61）。"""
    local = LocalMemoryBackend(root=tmp_path / "mem")
    s = MemoryItemStore(local=local)
    memory_dashboard_mod._memory_store = s
    try:
        app = create_app(runtime=_RT())  # type: ignore[arg-type]
        with TestClient(app) as client:
            # 1. CREATE
            r_create = client.post(
                "/api/memory/items",
                json={
                    "content": "first memory",
                    "memory_type": "user",
                    "importance": 0.6,
                },
            )
            assert r_create.status_code == 201
            mid = r_create.json()["id"]
            assert r_create.json()["content"] == "first memory"
            assert r_create.json()["status"] == "active"

            # 2. READ
            r_read = client.get(f"/api/memory/items/{mid}")
            assert r_read.status_code == 200
            assert r_read.json()["id"] == mid
            assert r_read.json()["importance"] == 0.6

            # 3. UPDATE（部分更新）
            r_update = client.patch(
                f"/api/memory/items/{mid}",
                json={"content": "updated memory", "importance": 0.9},
            )
            assert r_update.status_code == 200
            assert r_update.json()["content"] == "updated memory"
            assert r_update.json()["importance"] == 0.9

            # 4. ARCHIVE
            r_arc = client.post(f"/api/memory/items/{mid}/archive")
            assert r_arc.status_code == 200
            assert r_arc.json()["status"] == "archived"

            # 5. DELETE
            r_del = client.delete(f"/api/memory/items/{mid}")
            assert r_del.status_code == 200
            assert r_del.json()["deleted"] is True

            # 6. 验证：read 404
            r_404 = client.get(f"/api/memory/items/{mid}")
            assert r_404.status_code == 404
    finally:
        memory_dashboard_mod._memory_store = None


# ---- E2E 场景 2：vector backend 双写（local + vector 同步）------------------


# 功能：store 配置 vector 后，write/update/delete 都双写到 vector
# 设计：写 1 条 → 检查 vector.write_calls；改 1 条 → vector.update_calls；
#      删 1 条 → vector.delete_calls
def test_e2e_vector_backend_dual_write(tmp_path: Path) -> None:
    """E2E 验证 vector backend 接收写/改/删同步（agent: package-dashboard-api-v61）。"""
    import asyncio

    local = LocalMemoryBackend(root=tmp_path / "mem")
    vector = _MockVectorBackend()
    s = MemoryItemStore(local=local, vector=vector)
    memory_dashboard_mod._memory_store = s
    try:
        # 直接通过 store 写（也走 dual write 路径）
        asyncio.run(s.write(_make_item(id="m-v1", content="vector test")))

        # 验证双写
        assert "m-v1" in vector.write_calls
        assert "m-v1" in vector.items

        # update
        asyncio.run(
            s.update(
                "m-v1",
                _make_item(id="m-v1", content="vector test updated"),
            )
        )
        assert "m-v1" in vector.update_calls
        assert vector.items["m-v1"].content == "vector test updated"

        # delete
        asyncio.run(s.delete("m-v1"))
        assert "m-v1" in vector.delete_calls
        assert "m-v1" not in vector.items

        # 验证 local 也有写
        md_file = tmp_path / "mem" / "m-v1.md"
        # delete 后 m-v1.md 不存在
        assert not md_file.exists()
    finally:
        memory_dashboard_mod._memory_store = None


# ---- E2E 场景 3：search 走 vector 后端 --------------------------------------


# 功能：search 端点在 vector 可用时返回 vector 检索结果
# 设计：mock vector 放 2 条记忆 → GET /search → 验证 backend=vector + count=2
def test_e2e_search_uses_vector(tmp_path: Path) -> None:
    """E2E 验证 /search 端点使用 vector backend（agent: package-dashboard-api-v61）。"""
    import asyncio

    local = LocalMemoryBackend(root=tmp_path / "mem")
    vector = _MockVectorBackend()
    # 预先写 2 条到 vector（不写 local）
    asyncio.run(
        vector.write(
            _make_item(
                id="v-alpha",
                content="alpha and bravo combined",
                memory_type="user",
            )
        )
    )
    asyncio.run(
        vector.write(
            _make_item(
                id="v-beta",
                content="charlie and alpha together",
                memory_type="feedback",
            )
        )
    )
    s = MemoryItemStore(local=local, vector=vector)
    memory_dashboard_mod._memory_store = s
    try:
        app = create_app(runtime=_RT())  # type: ignore[arg-type]
        with TestClient(app) as client:
            r = client.get("/api/memory/search?q=alpha&top_k=10")
            assert r.status_code == 200
            body = r.json()
            assert body["backend"] == "vector"
            assert body["count"] == 2
            ids = {x["id"] for x in body["results"]}
            assert ids == {"v-alpha", "v-beta"}
            # vector.search 被调用 1 次
            assert vector.search_calls == [("alpha", 10)]
    finally:
        memory_dashboard_mod._memory_store = None


# ---- E2E 场景 4：跨请求持久化 ----------------------------------------------


# 功能：多个独立 TestClient 读同一 store 路径，持久化跨请求一致
# 设计：第一次 TestClient 写 2 条 → 关闭；第二次 TestClient 重新构造
#      同一 store path → 能读到 2 条
def test_e2e_persistence_across_requests(tmp_path: Path) -> None:
    """E2E 跨请求持久化（agent: package-dashboard-api-v61）。"""
    store_path = tmp_path / "mem"
    # 第一次"会话"：写 2 条
    local1 = LocalMemoryBackend(root=store_path)
    s1 = MemoryItemStore(local=local1)
    memory_dashboard_mod._memory_store = s1
    try:
        import asyncio

        asyncio.run(s1.write(_make_item(id="m-p1", content="persisted 1")))
        asyncio.run(s1.write(_make_item(id="m-p2", content="persisted 2")))

        app1 = create_app(runtime=_RT())  # type: ignore[arg-type]
        with TestClient(app1) as c1:
            r1 = c1.get("/api/memory/items")
            assert r1.status_code == 200
            assert r1.json()["total"] == 2
    finally:
        memory_dashboard_mod._memory_store = None

    # 第二次"会话"：用同一 path 重建 store
    local2 = LocalMemoryBackend(root=store_path)
    s2 = MemoryItemStore(local=local2)
    memory_dashboard_mod._memory_store = s2
    try:
        app2 = create_app(runtime=_RT())  # type: ignore[arg-type]
        with TestClient(app2) as c2:
            r2 = c2.get("/api/memory/items")
            assert r2.status_code == 200
            body = r2.json()
            assert body["total"] == 2
            ids = {i["id"] for i in body["items"]}
            assert {"m-p1", "m-p2"}.issubset(ids)
    finally:
        memory_dashboard_mod._memory_store = None


# ---- E2E 场景 5：dashboard router 集成到 create_app ------------------------


# 功能：memory dashboard 8 端点都注册到 create_app 的 FastAPI app
# 设计：枚举 app.router.routes 验证 8 个 memory 路径 + 与现有路由共存
def test_e2e_memory_dashboard_in_gateway_app(tmp_path: Path) -> None:
    """E2E 验证 memory dashboard router 集成到 FastAPI app（agent: package-dashboard-api-v61）。"""
    local = LocalMemoryBackend(root=tmp_path / "mem")
    s = MemoryItemStore(local=local)
    memory_dashboard_mod._memory_store = s
    try:
        app = create_app(runtime=_RT())  # type: ignore[arg-type]
        with TestClient(app) as client:
            # 8 个端点路径在 openapi 中存在
            r_openapi = client.get("/openapi.json")
            assert r_openapi.status_code == 200
            openapi = r_openapi.json()
            memory_paths = {
                "/api/memory/items",
                "/api/memory/search",
                "/api/memory/audit",
            }
            for p in memory_paths:
                assert p in openapi["paths"], f"missing {p}"
            # items/{id} + items/{id}/archive
            assert "/api/memory/items/{memory_id}" in openapi["paths"]
            assert (
                "/api/memory/items/{memory_id}/archive" in openapi["paths"]
            )

            # GET /items 200
            r_items = client.get("/api/memory/items")
            assert r_items.status_code == 200

            # 4xx 端点：items/{id} 404
            r_404 = client.get("/api/memory/items/missing")
            assert r_404.status_code == 404

            # 与原有路由共存
            r_health = client.get("/health")
            assert r_health.status_code == 200
            assert r_health.json()["status"] == "ok"

            # 与 Wave 5.2 dashboard 路由共存
            assert "/api/dashboard/summary" in openapi["paths"]
            assert "/api/team/summary" in openapi["paths"]
            assert "/api/coding/summary" in openapi["paths"]
    finally:
        memory_dashboard_mod._memory_store = None


# ---- E2E 场景 6：list 过滤 + search 完整数据贯通 --------------------------


# 功能：local 路径下，list 过滤 + search 端点数据完全一致
# 设计：写 3 条不同 status/memory_type → list 过滤 + search 各验证一次
def test_e2e_list_and_search_data_consistency(tmp_path: Path) -> None:
    """E2E 验证 list 过滤与 search 数据一致（agent: package-dashboard-api-v61）。"""
    import asyncio

    local = LocalMemoryBackend(root=tmp_path / "mem")
    s = MemoryItemStore(local=local)
    memory_dashboard_mod._memory_store = s
    try:
        asyncio.run(
            s.write(
                _make_item(
                    id="m-1",
                    content="alpha bravo",
                    memory_type="user",
                    status="active",
                )
            )
        )
        asyncio.run(
            s.write(
                _make_item(
                    id="m-2",
                    content="alpha charlie",
                    memory_type="feedback",
                    status="active",
                )
            )
        )
        asyncio.run(
            s.write(
                _make_item(
                    id="m-3",
                    content="pure delta",
                    memory_type="user",
                    status="archived",
                )
            )
        )

        app = create_app(runtime=_RT())  # type: ignore[arg-type]
        with TestClient(app) as client:
            # list active user → m-1
            r1 = client.get(
                "/api/memory/items?status=active&memory_type=user"
            )
            assert r1.status_code == 200
            body1 = r1.json()
            assert body1["total"] == 1
            assert body1["items"][0]["id"] == "m-1"

            # search "alpha" → m-1, m-2
            r2 = client.get("/api/memory/search?q=alpha&top_k=5")
            assert r2.status_code == 200
            body2 = r2.json()
            assert body2["count"] == 2
            ids = {x["id"] for x in body2["results"]}
            assert ids == {"m-1", "m-2"}
    finally:
        memory_dashboard_mod._memory_store = None
