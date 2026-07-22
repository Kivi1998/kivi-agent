"""FastAPI 路由层（Wave 1 / D 阶段 stub）。

所有路由都委托给 `AgentRuntime` 门面（`kivi_agent.core.gateway.runtime`），
不在路由层直接 import `kivi_agent.core.bus` 的具体类型。

路由清单（v1 + D 报告 §迁移矩阵 3 + 4 + 7）：
- POST   /sessions                  → start_session
- GET    /sessions                  → list_sessions
- GET    /sessions/{session_id}     → get_session
- POST   /sessions/{session_id}/cancel     → cancel_session (T5)
- POST   /sessions/{session_id}/commands   → send_command
- WS     /sessions/{session_id}/ws         → 事件流
"""
