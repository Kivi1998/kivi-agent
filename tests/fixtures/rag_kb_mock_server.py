"""FastAPI in-process rag-kb mock server（agent: package-e2e-real-v4）。

WT-F4 E2E 基础设施：本地启动一个模拟 rag-kb 服务，监听随机端口，
返回 mock sources。供 tests/e2e_real/test_rag_real.py 验证
``RagKbClient`` / ``RagQueryTool`` 在真实 http 模式下的端到端行为。

设计原则：
1. **in-process 启动**：不依赖外部服务，pytest 直接 ``InProcessRagKbServer().start()``
2. **随机端口**：每次启动用 uvicorn port=0，避免端口冲突
3. **RESTful 约定**：
   - ``POST /api/v1/search`` → 返回 ``{answer, rewritten_query, sources}``
   - ``GET  /health``        → 返回 ``{status, kb_id}``
4. **mock 数据可定制**：通过 ``custom_docs`` 参数注入测试场景需要的文档

依赖：仅 fastapi + uvicorn + threading，均为 dev optional（pyproject.toml 已声明）。
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Any

import uvicorn
from fastapi import FastAPI

# 演示版默认 mock 知识库（agent: package-e2e-real-v4）
# 选取原则：跨主题（综述 + 原理）+ 字段齐全（id/title/snippet/score/url）
DEFAULT_MOCK_DOCS: list[dict[str, Any]] = [
    {
        "id": "doc-rag-001",
        "title": "RAG 系统架构综述",
        "snippet": (
            "检索增强生成（RAG）系统标准架构：query rewrite → embedding → "
            "向量检索 → rerank → answer generation。"
        ),
        "score": 0.95,
        "url": "https://kb.example.com/rag/architecture",
    },
    {
        "id": "doc-embed-001",
        "title": "Embedding 与向量检索原理",
        "snippet": "Embedding 把文本映射到稠密向量空间；cosine 相似度排序取 top_k。",
        "score": 0.87,
        "url": "https://kb.example.com/embeddings/intro",
    },
    {
        "id": "doc-rerank-001",
        "title": "Rerank 与精排实践",
        "snippet": "Rerank 阶段用 cross-encoder 对初筛 top-100 重排，NDCG@10 通常 +15%。",
        "score": 0.81,
        "url": "https://kb.example.com/rerank/practice",
    },
]


# 构造 mock rag-kb FastAPI app（agent: package-e2e-real-v4）
def create_app(
    kb_id: str = "default",
    custom_docs: list[dict[str, Any]] | None = None,
) -> FastAPI:
    """构造 FastAPI app：模拟 rag-kb 服务。

    参数：
    - ``kb_id``: 知识库 ID（用于 /health 响应 + sources 标记）
    - ``custom_docs``: 自定义 mock 文档列表；None 时使用 ``DEFAULT_MOCK_DOCS``
    """
    docs = custom_docs if custom_docs is not None else DEFAULT_MOCK_DOCS
    app = FastAPI(
        title=f"rag-kb mock ({kb_id})",
        version="0.0.1",
        description="In-process FastAPI mock for kivi-agent Wave 4 E2E",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """健康检查端点：返回 ok + kb_id。"""
        return {"status": "ok", "kb_id": kb_id}

    @app.post("/api/v1/search")
    async def search(payload: dict[str, Any]) -> dict[str, Any]:
        """搜索端点：返回 answer + sources + rewritten_query。

        简单实现：忽略 payload.kb_id 是否匹配；直接返回全部 mock docs。
        生产 rag-kb 会做 query rewrite + 向量检索 + rerank + LLM answer 生成，
        本 mock 不模拟 LLM 生成，只回显 query + 拼接 answer 前缀。
        """
        query = str(payload.get("query", ""))
        kb_in = payload.get("kb_id")
        # 简单 rewrite：query + " [refined]" + 可选 kb 标签
        suffix = f" @kb[{kb_in}]" if kb_in else ""
        rewritten = f"{query} [refined]{suffix}"
        return {
            "answer": (
                f"基于 {len(docs)} 条知识片段的 mock 回答：{query}。"
                f"（rag-kb mock; kb_id={kb_id}）"
            ),
            "rewritten_query": rewritten,
            "sources": docs,
        }

    return app


# in-process 后台启动器（agent: package-e2e-real-v4）
class InProcessRagKbServer:
    """in-process 启动的 rag-kb mock server。

    用法：
    ```python
    server = InProcessRagKbServer()
    base_url = server.start()
    # ... 用 base_url 调 /api/v1/search ...
    server.stop()
    ```
    """

    def __init__(
        self,
        kb_id: str = "default",
        custom_docs: list[dict[str, Any]] | None = None,
    ) -> None:
        """构造 server 实例（不启动），保存配置。"""
        self._kb_id = kb_id
        self._custom_docs = custom_docs
        self._app = create_app(kb_id=kb_id, custom_docs=custom_docs)
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._port: int = 0

    # 启动后台 server 并返回 base_url（agent: package-e2e-real-v4）
    def start(self, host: str = "127.0.0.1", port: int = 0) -> str:
        """后台线程启动 uvicorn，等待服务就绪后返回 base_url。

        参数：
        - ``host``: 绑定地址，默认 127.0.0.1
        - ``port``: 绑定端口，0 = 由 OS 分配随机端口

        返回：``http://{host}:{actual_port}`` base URL。
        """
        config = uvicorn.Config(
            self._app,
            host=host,
            port=port,
            log_level="error",
            access_log=False,
            lifespan="on",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run,
            daemon=True,
            name=f"rag-kb-mock-{self._kb_id}",
        )
        self._thread.start()
        # 等待 server.started 标志位（uvicorn 内部）
        for _ in range(100):  # 最多 ~10s
            if self._server.started:
                break
            time.sleep(0.1)
        else:
            self._cleanup_on_failure()
            raise RuntimeError(
                f"rag-kb mock server failed to start within 10s (kb_id={self._kb_id})"
            )
        # 端口探测：优先用 server.servers[0]（uvicorn 内部 sockets）
        self._port = self._discover_port()
        # 再次确认端口可连接（防御 uvicorn 内部时序）
        self._wait_for_connect(host, self._port, timeout_s=5.0)
        return f"http://{host}:{self._port}"

    # 停止后台 server（agent: package-e2e-real-v4）
    def stop(self) -> None:
        """通过 uvicorn should_exit 标志位触发优雅停机，等线程退出。"""
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._server = None
        self._thread = None
        self._port = 0

    # 获取实际绑定端口（agent: package-e2e-real-v4）
    @property
    def port(self) -> int:
        """返回 start() 后实际绑定的端口；未启动返回 0。"""
        return self._port

    # 探测端口（uvicorn 0.30+ 用 servers[0].sockets；旧版用 server.sockets）
    def _discover_port(self) -> int:
        """从 uvicorn 内部 sockets 拿真实端口，失败则 socket 探测。"""
        assert self._server is not None
        # 路径 1：uvicorn.Server.servers 列表（>=0.30）
        servers = getattr(self._server, "servers", None)
        if servers:
            for srv in servers:
                sockets = getattr(srv, "sockets", None)
                if sockets:
                    port_any: Any = sockets[0].getsockname()[1]
                    return int(port_any)
        # 路径 2：直接看 server.sockets（旧版）
        direct_sockets = getattr(self._server, "sockets", None)
        if direct_sockets:
            port_any = direct_sockets[0].getsockname()[1]
            return int(port_any)
        # 路径 3：兜底 — 探测配置端口（适用于 0 端口场景中 uvicorn 已记录）
        config = getattr(self._server, "config", None)
        if config is not None:
            configured = getattr(config, "port", 0)
            if configured and configured > 0:
                return int(configured)
        raise RuntimeError("Cannot discover bound port from uvicorn server")

    # 探测端口可达性（agent: package-e2e-real-v4）
    def _wait_for_connect(self, host: str, port: int, timeout_s: float) -> None:
        """TCP 探测端口直到可连或超时。"""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((host, port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError(f"rag-kb mock port {port} not connectable after start()")

    # 启动失败时清理资源（agent: package-e2e-real-v4）
    def _cleanup_on_failure(self) -> None:
        """启动超时时调 stop() 释放线程，避免 pytest 退出 hang。"""
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None


__all__ = [
    "DEFAULT_MOCK_DOCS",
    "InProcessRagKbServer",
    "create_app",
]
