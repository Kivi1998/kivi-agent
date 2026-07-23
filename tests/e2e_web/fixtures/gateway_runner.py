"""Gateway runner — 启动 FastAPI 并注入 FakeAgentRuntime（agent: package-web-e2e-v3）。

WT-E5 用：Playwright webServer 启动本脚本，listen 8000 端口。
脚本退出 = 服务停止（uvicorn.run 是阻塞的）。

**架构注**：``kivi_agent.core.gateway.ws_bridge.WebSocketBridge`` 本身不订阅
runtime 事件流 — 它只是个事件分发 hub（``publish()`` 推送到 client queues）。
真实链路下，由 WT-E1 范围内的事件桥接代码把 Adapter 事件流接进来。
WT-E5 因为没有真 kivi-core runtime，所以本脚本包一层 ``_PumpingBridge``：
- 复用 ``WebSocketBridge`` 的 queue 管理逻辑
- 在 ``connect()`` 期间启动后台 task，订阅 ``FakeAgentRuntime`` 事件并转发给 bridge
- 客户端断开时取消订阅 task
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn

# 把 repo 根加进 sys.path，让 kivi_agent.* 可 import
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fake_runtime import FakeAgentRuntime  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from kivi_agent.core.gateway.runtime import AgentRuntime  # noqa: E402
from kivi_agent.core.gateway.ws_bridge import WebSocketBridge  # noqa: E402
from kivi_agent.gateway.main import create_app  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gateway_runner")


class _PumpingBridge:
    """包装 WebSocketBridge，每个 connect() 启动一个订阅 task 把 runtime 事件推给桥。

    接口与 WebSocketBridge 完全兼容（connect / active_connections），
    所以可原样替换 ``app.state.ws_bridge``。
    """

    def __init__(self, runtime: AgentRuntime, inner: WebSocketBridge) -> None:
        self._runtime = runtime
        self._inner = inner
        # 维护 connect() 期间启动的订阅 task
        self._tasks: list[asyncio.Task[None]] = []

    @asynccontextmanager
    async def connect(self, session_id: str) -> AsyncIterator[Any]:
        """复用 inner.connect，但额外启动订阅 task 把 runtime 事件转发给 bridge。"""
        # 启动后台订阅 task
        task = asyncio.create_task(self._pump(session_id))
        self._tasks.append(task)
        try:
            async with self._inner.connect(session_id) as conn:
                yield conn
        finally:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            if task in self._tasks:
                self._tasks.remove(task)

    async def _pump(self, session_id: str) -> None:
        """订阅 runtime 事件并转发给 inner bridge。"""
        try:
            async for event in self._runtime.subscribe_events(session_id):
                await self._inner.publish(event)
        except asyncio.CancelledError:
            # 正常退出（connect 上下文关闭）
            pass
        except Exception as e:  # noqa: BLE001
            logger.warning("pump error for session=%s: %s", session_id, e)

    def active_connections(self) -> int:
        return self._inner.active_connections()


def main() -> None:
    port = int(os.environ.get("GATEWAY_PORT", "8000"))
    host = os.environ.get("GATEWAY_HOST", "127.0.0.1")

    runtime = FakeAgentRuntime()
    app = create_app(runtime=runtime)

    # CORS：测试页 5173 跨域调 8000
    # 真实生产由 Vite proxy 同源转发，不需要 CORS；这里仅 E2E 用
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 用 _PumpingBridge 替换 app.state.ws_bridge（gateway WS 路由会通过 deps 拿）
    inner_bridge = WebSocketBridge(runtime=runtime)
    app.state.ws_bridge = _PumpingBridge(runtime=runtime, inner=inner_bridge)

    logger.info("Starting FastAPI Gateway on %s:%d (FakeAgentRuntime + PumpingBridge)", host, port)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="warning",  # 减少噪音；启动信息由本 logger 输出
        access_log=False,
    )


if __name__ == "__main__":
    main()
