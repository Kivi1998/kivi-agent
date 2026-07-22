from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from kama_claude.core.session.checkpoint import CheckpointData, CheckpointStore
from kama_claude.core.session.model import Session
from kama_claude.core.session.store import SessionStore


# 渲染一行会话摘要：标题 + 最近检查点的 step/status（无检查点时给出明确提示）
def format_session_row(session: Session, checkpoint: CheckpointData | None) -> str:
    progress = f"step {checkpoint.step} ({checkpoint.status})" if checkpoint else "no progress yet"
    return f"[bold]{session.title or session.id}[/bold]  [dim]{session.id}[/dim]  {progress}"


class SessionListScreen(Screen[None]):
    """列出所有历史会话及其检查点进度；只读展示，关闭后用户可手动用 kama-tui --replay 恢复。"""

    BINDINGS = [Binding("escape", "dismiss", "close")]

    # 注入会话存储和检查点存储
    def __init__(self, session_store: SessionStore, checkpoint_store: CheckpointStore) -> None:
        super().__init__()
        self._session_store = session_store
        self._checkpoint_store = checkpoint_store

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="session-list")

    def on_mount(self) -> None:
        container = self.query_one("#session-list", VerticalScroll)
        sessions = self._session_store.list_sessions()
        if not sessions:
            container.mount(Static("[dim]no sessions yet[/dim]"))
            return
        for session in sessions:
            checkpoint = None
            if session.run_ids:
                checkpoint = self._checkpoint_store.load(session.id, session.run_ids[-1])
            container.mount(Static(format_session_row(session, checkpoint)))
