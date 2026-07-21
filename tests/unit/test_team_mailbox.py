from __future__ import annotations

from pathlib import Path

from kama_claude.core.teams.mailbox import consume_messages, write_message


# 功能：验证写入一条消息后，收件人能通过 consume_messages 读到，且读取后消息被清空
# 设计："consume"语义是取走即删除，覆盖"读两次第二次应该是空"这个核心行为
def test_write_then_consume_drains_mailbox(tmp_path: Path) -> None:
    write_message(tmp_path, recipient="executor", sender="planner", content="先看 auth.py")
    messages = consume_messages(tmp_path, "executor")
    assert len(messages) == 1
    assert messages[0]["sender"] == "planner"
    assert messages[0]["content"] == "先看 auth.py"

    second_read = consume_messages(tmp_path, "executor")
    assert second_read == []


# 功能：验证同一收件人收到的多条消息按写入顺序全部返回
# 设计：team_message 可能被连续调用多次，消费时不能丢消息也不能乱序
def test_multiple_messages_preserved_in_order(tmp_path: Path) -> None:
    write_message(tmp_path, recipient="executor", sender="planner", content="first")
    write_message(tmp_path, recipient="executor", sender="planner", content="second")
    messages = consume_messages(tmp_path, "executor")
    assert [m["content"] for m in messages] == ["first", "second"]


# 功能：验证给不同收件人写的消息互不干扰
# 设计：mailbox 按收件人隔离，覆盖"executor 消费不会拿到 reviewer 的信"这个边界
def test_messages_isolated_per_recipient(tmp_path: Path) -> None:
    write_message(tmp_path, recipient="executor", sender="planner", content="for executor")
    write_message(tmp_path, recipient="reviewer", sender="planner", content="for reviewer")
    assert [m["content"] for m in consume_messages(tmp_path, "executor")] == ["for executor"]
    assert [m["content"] for m in consume_messages(tmp_path, "reviewer")] == ["for reviewer"]
