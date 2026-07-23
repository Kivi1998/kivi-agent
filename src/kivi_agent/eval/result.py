"""评测结果（agent: package-eval-dataset-v51）。

# result.py（agent: package-eval-dataset-v51）
单 case 跑完后的全量信息：路由决策、工具调用、引用、事件流、token、Judge 评分。
- EvalResult：case 顶层结果
- ToolCallRecord：单次 tool 调用记录
- CaseEvent：单 case 事件（按时间排序）
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


# 工具调用记录（agent: package-eval-dataset-v51）
class ToolCallRecord(BaseModel):
    """单次工具调用记录。

    字段映射 v1 §5.2.1 三个 tool 事件：
    - tool.call_started → started_at
    - tool.call_finished → finished_at + success
    - tool.call_failed → finished_at + success=False + error
    """

    tool_name: str
    started_at: str
    finished_at: str | None = None
    success: bool = True
    error: str | None = None
    elapsed_ms: int | None = None


# 单 case 事件记录（agent: package-eval-dataset-v51）
class CaseEvent(BaseModel):
    """单 case 事件记录。

    字段与 v1 §5.2.1 6 事件对齐：
    - run.started / run.finished（包络）
    - tool.call_started / tool.call_finished / tool.call_failed
    - rag.sources_cited / chart.rendered
    """

    type: str
    ts: str
    data: dict[str, Any] = Field(default_factory=dict)


# 单 case 评测结果（agent: package-eval-dataset-v51）
class EvalResult(BaseModel):
    """单 case 评测结果。

    设计要点（与 WT-G1 plan §三 一致）：
    - route_decision：BusinessRouter.route() 的 RouteDecision 序列化为 dict
    - tool_calls：单 case 内全部 tool 调用记录
    - rag_sources：实际触发的 RAG 引用（id / title / snippet / score）
    - chart_metadata：实际生成的图表元数据
    - input/output/cache tokens：成本计算 + G2 指标用
    - judge_score / judge_reason：Judge 评分（0-1）+ 理由
    - events：按时间排序的事件流（前端时间轴用）
    """

    case_id: str
    run_id: str
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    success: bool = False
    error: str | None = None
    # 路由决策（RouteDecision 的 dict 形态）
    route_decision: dict[str, Any] | None = None
    # 工具调用
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    # RAG / Chart 实际数据
    rag_sources: list[dict[str, Any]] = Field(default_factory=list)
    chart_metadata: list[dict[str, Any]] = Field(default_factory=list)
    # 最终输出
    final_answer: str | None = None
    # Token（成本计算 + G2 指标用）
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    # Judge
    judge_score: float | None = None
    judge_reason: str | None = None
    # 事件流（按时间排序）
    events: list[CaseEvent] = Field(default_factory=list)
