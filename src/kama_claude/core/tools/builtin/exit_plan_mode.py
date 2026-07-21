from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from kama_claude.core.tools.base import BaseTool, ToolResult


class ExitPlanModeParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    plan_summary: str


class ExitPlanModeTool(BaseTool):
    params_model = ExitPlanModeParams
    name = "exit_plan_mode"
    category = "other"
    description = (
        "Call this when you have finished planning in plan mode and are ready to present "
        "the plan to the user for approval before executing it. Pass a concise summary of "
        "the plan. This tool does not execute anything by itself — the caller decides "
        "whether to switch out of plan mode based on the user's response."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "plan_summary": {"type": "string", "description": "Concise summary of the plan to present."},
        },
        "required": ["plan_summary"],
    }

    # 返回计划摘要的确认文本；不直接修改权限模式，模式切换由调用方驱动
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = ExitPlanModeParams.model_validate(params)
        return ToolResult(
            content=f"Plan ready for review:\n\n{p.plan_summary}\n\nAwaiting user decision."
        )
