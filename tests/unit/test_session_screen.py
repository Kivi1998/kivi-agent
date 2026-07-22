from __future__ import annotations

from kivi_agent.core.session.checkpoint import CheckpointData
from kivi_agent.core.session.model import Session
from kivi_agent.tui.session_screen import format_session_row


# 功能：验证有检查点时，展示行包含 session 标题和检查点的 step/status 信息
# 设计：这是用户在会话列表界面判断"这个会话上次跑到哪一步、能不能继续"的关键信息来源
def test_format_row_with_checkpoint_shows_progress() -> None:
    session = Session(
        id="s1", mode="chat", status="active", title="修复登录 bug",
        created_at="t", updated_at="t",
    )
    checkpoint = CheckpointData(run_id="r1", step=3, status="running", message_count=10, ts="t")
    row = format_session_row(session, checkpoint)
    assert "修复登录 bug" in row
    assert "step 3" in row
    assert "running" in row


# 功能：验证没有检查点时（比如会话从未跑过任何 run）展示行不报错，给出明确的"无进度"提示
# 设计：覆盖新建但还没发过消息的会话这个边界状态
def test_format_row_without_checkpoint_shows_no_progress() -> None:
    session = Session(
        id="s2", mode="chat", status="active", title="新会话",
        created_at="t", updated_at="t",
    )
    row = format_session_row(session, None)
    assert "新会话" in row
    assert "no progress" in row.lower()
