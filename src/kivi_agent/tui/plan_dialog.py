from __future__ import annotations

import re
from collections.abc import Iterable

from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Button, Static

_PLAN_OUTPUT_RE = re.compile(
    r"^Plan ready for review:\n\n(.*)\n\nAwaiting user decision\.$", re.DOTALL
)


# 从 exit_plan_mode 工具的标准输出文本里提取纯计划内容；格式不匹配时原样返回整段文本
def parse_plan_summary(tool_output: str) -> str:
    match = _PLAN_OUTPUT_RE.match(tool_output)
    return match.group(1) if match else tool_output


class PlanDialog(Vertical):
    """展示待审批的计划摘要，提供 Accept/Reject 两个按钮。"""

    # 用计划摘要文本初始化对话框
    def __init__(self, plan_summary: str) -> None:
        super().__init__(id="plan-dialog")
        self._plan_summary = plan_summary

    def compose(self) -> Iterable[Widget]:
        yield Static(f"[bold]Plan:[/bold]\n{self._plan_summary}")
        with Vertical():
            yield Button("Accept — exit plan mode", id="plan-accept", variant="success")
            yield Button("Reject — stay in plan mode", id="plan-reject", variant="error")
