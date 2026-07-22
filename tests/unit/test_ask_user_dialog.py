from __future__ import annotations

from typing import Any

from kama_claude.tui.ask_user_dialog import AskUserDialog


# 功能：验证选项数量 > 0 时，对话框渲染包含所有选项文本
# 设计：直接调 _render_ui 拿到富文本字符串，断言每个选项 label 都出现，
#      覆盖"渲染分支走的是 options 分支"这个关键路径
def test_render_includes_all_options() -> None:
    dlg = AskUserDialog("q1", "Continue?", ["yes", "no"])
    text = dlg._render_ui()
    assert "yes" in text
    assert "no" in text
    assert "Continue?" in text


# 功能：验证 free-form 模式（options 为空）渲染时提示"输入答案"而不是列出选项
# 设计：options=[] 时必须显示文本输入提示，否则用户在 TUI 看到空弹窗会困惑
def test_render_free_form_shows_input_prompt() -> None:
    dlg = AskUserDialog("q1", "你偏好哪种风格？", [])
    text = dlg._render_ui()
    assert "你偏好哪种风格？" in text
    assert "input" in text.lower() or "输入" in text


# 功能：验证 Answered 消息携带 request_id 和选中的选项
# 设计：直接调 _pick 模拟用户按数字键 1，断言 post_message 被调用且参数正确；
#      这里用 monkeypatch 替换 post_message 来捕获，避免起完整 App
def test_pick_emits_answered_message(monkeypatch: Any) -> None:
    dlg = AskUserDialog("q1", "Continue?", ["yes", "no"])
    captured: list[Any] = []
    monkeypatch.setattr(dlg, "post_message", lambda m: captured.append(m))

    dlg._pick("yes")

    assert len(captured) == 1
    msg = captured[0]
    assert msg.request_id == "q1"
    assert msg.answer == "yes"


# 功能：验证上下方向键改变 _cursor 索引并循环
# 设计：模拟两次 down 再 up，断言 _cursor 在 [0, 1, 2, 0, 1, ...] 范围内循环，
#      避免"光标到底就卡住"的边界 bug
def test_cursor_wraps_around() -> None:
    dlg = AskUserDialog("q1", "?", ["a", "b", "c"])
    assert dlg._cursor == 0
    dlg._move_cursor(+1)
    assert dlg._cursor == 1
    dlg._move_cursor(+1)
    assert dlg._cursor == 2
    dlg._move_cursor(+1)  # 越界回绕
    assert dlg._cursor == 0
    dlg._move_cursor(-1)  # 负向回绕
    assert dlg._cursor == 2
