"""kivi-agent Gateway（顶层 FastAPI 骨架，Wave 1 / D 阶段）。

与 `kivi_agent.core.gateway`（Protocol + Adapter + WS Bridge）的区别：
- `core.gateway` 是与 core 守护进程交互的内部实现层（不依赖 FastAPI）
- `gateway` 是暴露给 Web 前端的 HTTP / WebSocket 入口（依赖 FastAPI）

FastAPI / uvicorn / websockets 是 dev optional 依赖：未安装时，
`kivi-agent` 仍可作为 kivi-core 守护进程 + TUI / CLI 客户端正常运行。
"""

from kivi_agent.gateway.main import create_app

__all__ = ["create_app"]
