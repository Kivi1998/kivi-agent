from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from kama_claude.core.teams.mailbox import write_message
from kama_claude.core.tools.base import BaseTool, ToolResult


class TeamMessageParams(BaseModel):
    model_config = ConfigDict(extra="ignore")
    to: str
    sender: str
    content: str


class TeamMessageTool(BaseTool):
    params_model = TeamMessageParams
    name = "team_message"
    category = "other"
    description = (
        "Send a message to another team member by name. The recipient will see it the next "
        "time it checks its mailbox (sub-agents should call this tool themselves to check in)."
    )
    input_schema: dict[str, object] = {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient member name."},
            "sender": {"type": "string", "description": "Your own member name."},
            "content": {"type": "string", "description": "Message content."},
        },
        "required": ["to", "sender", "content"],
    }

    # 注入 mailbox 根目录（通常是 session 的 runs 目录）
    def __init__(self, mailbox_root: Path) -> None:
        self._mailbox_root = mailbox_root

    # 把消息写入收件人的 mailbox
    async def invoke(self, params: dict[str, object]) -> ToolResult:
        p = TeamMessageParams.model_validate(params)
        write_message(self._mailbox_root, recipient=p.to, sender=p.sender, content=p.content)
        return ToolResult(content=f"message sent to {p.to}")
