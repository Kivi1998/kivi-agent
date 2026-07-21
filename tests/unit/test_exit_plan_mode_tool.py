from __future__ import annotations

from kama_claude.core.tools.builtin.exit_plan_mode import ExitPlanModeTool


# 功能：验证工具调用时返回的确认文本包含提交的计划摘要
# 设计：只测试工具的纯文本输出，不测试模式切换本身（切换发生在调用方，不在这个工具里）
async def test_exit_plan_mode_returns_confirmation_with_summary() -> None:
    result = await ExitPlanModeTool().invoke({"plan_summary": "先加测试再实现"})
    assert not result.is_error
    assert "先加测试再实现" in result.content
