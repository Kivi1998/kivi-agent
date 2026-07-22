from __future__ import annotations

from textual import events
from textual.app import App, ComposeResult
from textual.message import Message
from textual.widgets import Input, Static


# 复用 TUI 现有的 PermissionSelect 风格（Static 子类 + Decided Message），
# 但题面渲染走 options / free-form 分支，提交方式有"选项"和"自由输入"两种
class AskUserDialog(Static):
    """内联 ask_user 弹窗：列出选项或提供输入框，用户决策后 post_message。"""

    can_focus = True

    DEFAULT_CSS = """
    AskUserDialog {
        height: auto;
        padding: 1 2;
        margin-bottom: 1;
        border: round cyan;
    }
    """

    # 用户作出选择时发布；app 负责把这个消息转成 IPC 回包调 question_store.respond()
    class Answered(Message):
        # 初始化 Answered 消息，存储 request_id 和答案字符串
        def __init__(self, widget: AskUserDialog, request_id: str, answer: str) -> None:
            self.widget = widget
            self.request_id = request_id
            self.answer = answer
            super().__init__()

    # 初始化：保存 request_id、题面、选项列表，初始光标在第一项
    def __init__(self, request_id: str, question: str, options: list[str]) -> None:
        super().__init__("")
        self._request_id = request_id
        self._question = question
        self._options = list(options)
        self._cursor = 0
        self._input_widget: Input | None = None  # free-form 时挂的输入框

    def compose(self) -> ComposeResult:
        if self._options:
            yield Static(self._render_options(), classes="ask-user-options")
        else:
            self._input_widget = Input(placeholder="输入你的答案后按 enter")
            yield self._input_widget

    # 渲染 options 分支的富文本（光标高亮 + 快捷键提示）
    def _render_options(self) -> str:
        lines: list[str] = [f"[bold]?[/bold] {self._question}", ""]
        for i, opt in enumerate(self._options):
            if i == self._cursor:
                lines.append(f"  [bold cyan]❯ {i + 1}. {opt}[/bold cyan]")
            else:
                lines.append(f"    {i + 1}. {opt}")
        lines.append("[dim]  ↑↓ navigate   enter confirm   1-9 jump[/dim]")
        return "\n".join(lines)

    # 渲染 free-form 分支（compose 里直接挂 Input 控件，此处只返回题面文本）
    def _render_ui(self) -> str:
        if not self._options:
            return f"[bold]?[/bold] {self._question}\n[dim]  输入答案后按 enter[/dim]"
        return self._render_options()

    # 移动光标（+1 向下、-1 向上）；索引越界时回绕而不是夹紧
    def _move_cursor(self, delta: int) -> None:
        n = len(self._options)
        if n == 0:
            return
        self._cursor = (self._cursor + delta) % n
        self.update(self._render_options())

    # options 分支的键盘处理：方向键移动、数字键跳转、enter 确认
    def on_key(self, event: events.Key) -> None:
        if not self._options:
            return  # free-form 模式让 Input 控件自己处理
        key = event.key
        if key in ("up", "k"):
            event.stop()
            self._move_cursor(-1)
        elif key in ("down", "j"):
            event.stop()
            self._move_cursor(+1)
        elif key == "enter":
            event.stop()
            self._pick(self._options[self._cursor])
        elif key.isdigit():
            idx = int(key) - 1
            if 0 <= idx < len(self._options):
                event.stop()
                self._pick(self._options[idx])

    # Input 控件提交时（free-form 模式），从 Input.value 取答案并 post_message
    def on_input_submitted(self, event: Input.Submitted) -> None:
        answer = event.value.strip()
        if not answer:
            return
        self._pick(answer)

    # 把决策包成 Answered 消息发出；app 收到后会通过 IPC 调 question_store.respond()
    def _pick(self, answer: str) -> None:
        self.post_message(self.Answered(self, self._request_id, answer))


# 工厂函数：在 app 里挂一个 AskUserDialog 到 prompt 上方，并把 on_answer 回调挂上。
# 单独抽出来方便在 Answered 消息里直接调 app.call_later / run_worker 转发。
def mount_dialog(
    app: App[None],
    request_id: str,
    question: str,
    options: list[str],
) -> AskUserDialog:
    dlg = AskUserDialog(request_id, question, options)
    app.mount(dlg, before="#prompt")
    dlg.focus()
    return dlg
