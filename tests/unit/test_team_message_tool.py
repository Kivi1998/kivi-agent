from __future__ import annotations

from pathlib import Path

from kivi_agent.core.teams.mailbox import consume_messages
from kivi_agent.core.tools.builtin.team_message import TeamMessageTool


# 功能：验证工具调用后消息真的写进了对应收件人的 mailbox
# 设计：调用工具后直接用 mailbox 的读取函数验证落盘内容，覆盖"工具是 mailbox.write_message 的薄封装"这一层
async def test_team_message_writes_to_mailbox(tmp_path: Path) -> None:
    tool = TeamMessageTool(mailbox_root=tmp_path)
    result = await tool.invoke({"to": "executor", "sender": "planner", "content": "先看 auth.py"})
    assert not result.is_error
    messages = consume_messages(tmp_path, "executor")
    assert messages[0]["content"] == "先看 auth.py"
