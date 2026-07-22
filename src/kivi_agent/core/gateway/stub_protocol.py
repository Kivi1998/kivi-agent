"""Wave 1 协议 stub。

按 v1 契约 §5.2，A 阶段需要在 `core/bus/events.py` 新增 6 个事件，
在 `core/bus/commands.py` 新增 `SessionCancelCommand/Result` 命令组。

当前 main @ d31e0b2 A 阶段尚未 commit。为避免 D 阶段阻塞，本模块
在 D 自己的 gateway 包内复制协议 stub，**仅供 D 阶段代码使用**：

- Adapter / FastAPI 路由层 import 本模块以引用新事件 / 命令；
- A 阶段合并到 main 后，主控 Agent 切换 import 路径到 `core/bus/`，并删除本文件。

**删除时机**：`git log main --oneline` 出现 A 阶段 6 事件 / SessionCancel 的
commit 后即可在主控 Agent 主导下删除本文件。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


# ---- 6 个新事件（v1 §5.2.1） ----

class LlmThinkingEvent(BaseModel):
    """LLM 推理内容（区别于 LlmTokenEvent，承载 DeepSeek reasoning_content 等思考流）。"""

    type: Literal["llm.thinking"] = "llm.thinking"
    run_id: str
    chunk: str
    ts: str


class ChartRenderedEvent(BaseModel):
    """C 阶段 Chart Tool 生成的 ECharts 图表元数据。"""

    type: Literal["chart.rendered"] = "chart.rendered"
    run_id: str
    chart_type: str
    option: dict[str, Any]
    ts: str


class RagSourcesCitedEvent(BaseModel):
    """C 阶段 RAG Tool 引用溯源。"""

    type: Literal["rag.sources_cited"] = "rag.sources_cited"
    run_id: str
    sources: list[dict[str, Any]]  # 与 aigroup ReferenceSource 对齐
    ts: str


class FrontendToolCallRequested(BaseModel):
    """Core 通知 Web 前端：Agent 调用了一个前端 MCP 工具。"""

    type: Literal["frontend_tool.call_requested"] = "frontend_tool.call_requested"
    run_id: str
    request_id: str
    tool_name: str
    tool_args: dict[str, Any]
    ts: str


class FrontendToolCallResponded(BaseModel):
    """Core 通知 Web 前端：前端 MCP 工具的响应已回写到 Agent。"""

    type: Literal["frontend_tool.call_responded"] = "frontend_tool.call_responded"
    run_id: str
    request_id: str
    status: str  # "ok" | "error"
    content: dict[str, Any]
    ts: str


class RunCancelledEvent(BaseModel):
    """Run 已被取消（用户主动 / 超时 / 取消按钮）。"""

    type: Literal["run.cancelled"] = "run.cancelled"
    run_id: str
    reason: str
    ts: str


# ---- SessionCancel 命令组（v1 §5.2.2） ----

class SessionCancelCommand(BaseModel):
    """取消一个 session 当前正在运行的 run。"""

    type: Literal["session.cancel"] = "session.cancel"
    session_id: str
    reason: str = ""


class SessionCancelResult(BaseModel):
    """session.cancel 的结果。"""

    cancelled: bool
    session_id: str
    ts: str
