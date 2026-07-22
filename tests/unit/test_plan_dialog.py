from __future__ import annotations

from kama_claude.tui.plan_dialog import parse_plan_summary


# 功能：验证从 exit_plan_mode 工具的标准输出文本里正确提取出纯计划内容
# 设计：exit_plan_mode.py（包 D）的输出格式是固定的
#      "Plan ready for review:\n\n{summary}\n\nAwaiting user decision."，
#      对话框只需要中间那部分，覆盖这个字符串提取逻辑
def test_parse_plan_summary_extracts_middle_content() -> None:
    tool_output = "Plan ready for review:\n\n先加测试再实现\n\nAwaiting user decision."
    assert parse_plan_summary(tool_output) == "先加测试再实现"


# 功能：验证输出格式不符合预期时，原样返回整段文本而不是抛异常或返回空
# 设计：容错兜底——格式万一变了，对话框至少还能展示点什么，而不是白屏
def test_parse_plan_summary_falls_back_to_raw_text_on_mismatch() -> None:
    assert parse_plan_summary("unexpected format") == "unexpected format"
