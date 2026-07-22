from __future__ import annotations

from pathlib import Path

from kivi_agent.core.compact.budget import persist_and_truncate_tool_results, truncate_tool_results


def _make_tool_result_msg(content: str) -> dict:
    return {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "id1", "content": content}],
    }


# 功能：验证 tool_result 内容未超过阈值时原文不变
# 设计：构造 7999 字符内容（刚好低于 8000），断言消息原样返回
def test_short_tool_result_untouched() -> None:
    text = "x" * 7999
    msgs = [_make_tool_result_msg(text)]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    assert result[0]["content"][0]["content"] == text


# 功能：验证 tool_result 内容超过阈值时被截断并附加省略标记
# 设计：构造 10000 字符内容，断言截断后长度 < 原始，且包含省略标记字符串
def test_long_tool_result_truncated() -> None:
    text = "y" * 10_000
    msgs = [_make_tool_result_msg(text)]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    truncated = result[0]["content"][0]["content"]
    assert len(truncated) < len(text)
    assert "chars omitted" in truncated
    assert truncated.startswith("y" * 4000)


# 功能：验证 tool_result 内容恰好等于阈值时不截断
# 设计：构造恰好 8000 字符内容，断言原文保持不变
def test_exact_limit_untouched() -> None:
    text = "z" * 8000
    msgs = [_make_tool_result_msg(text)]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    assert result[0]["content"][0]["content"] == text


# 功能：验证 text 类型 block 不受截断影响
# 设计：构造含 text block 的 user 消息，内容超过阈值，断言内容原样返回
def test_non_tool_result_block_untouched() -> None:
    long_text = "a" * 20_000
    msgs = [{"role": "user", "content": [{"type": "text", "text": long_text}]}]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    assert result[0]["content"][0]["text"] == long_text


# 功能：验证同一 user 消息含多个 tool_result 时各自独立判断截断
# 设计：构造一条消息含两个 tool_result，一短一长，断言只有长的被截断
def test_multiple_tool_results_independent() -> None:
    short = "s" * 100
    long = "l" * 10_000
    msgs = [{
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "a", "content": short},
            {"type": "tool_result", "tool_use_id": "b", "content": long},
        ],
    }]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    blocks = result[0]["content"]
    assert blocks[0]["content"] == short
    assert "chars omitted" in blocks[1]["content"]


# 功能：验证 assistant 消息不被截断处理
# 设计：构造超长内容的 assistant 消息，断言原样返回
def test_assistant_message_untouched() -> None:
    text = "a" * 20_000
    msgs = [{"role": "assistant", "content": text}]
    result = truncate_tool_results(msgs, limit=8000, keep=4000)
    assert result[0]["content"] == text


# 功能：验证超限的 tool_result 内容被落盘到 session_dir/tool_outputs/ 下，对话里替换成引用占位符
# 设计：构造一条超过 limit 的 tool_result 消息，断言落盘文件内容和原文完全一致（不丢数据），
#      对话里的占位符文本包含落盘文件的相对路径，确保可以顺藤摸瓜找回完整内容
def test_oversized_tool_result_is_persisted_with_placeholder(tmp_path: Path) -> None:
    long_text = "x" * 20_000
    messages = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": long_text}
    ]}]
    result = persist_and_truncate_tool_results(messages, tmp_path, limit=8_000)
    block = result[0]["content"][0]
    assert "tool_outputs/" in block["content"]
    assert "20000" not in block["content"] or "chars" in block["content"]
    persisted_files = list((tmp_path / "tool_outputs").glob("*.txt"))
    assert len(persisted_files) == 1
    assert persisted_files[0].read_text(encoding="utf-8") == long_text


# 功能：验证未超限的 tool_result 原样保留，不产生落盘文件
# 设计：短文本消息走同一函数，断言内容不变且 tool_outputs 目录不存在，
#      覆盖"没有超限就不该有任何副作用"这个边界
def test_short_tool_result_is_untouched(tmp_path: Path) -> None:
    messages = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "short"}
    ]}]
    result = persist_and_truncate_tool_results(messages, tmp_path, limit=8_000)
    assert result[0]["content"][0]["content"] == "short"
    assert not (tmp_path / "tool_outputs").exists()


# 功能：验证超限 tool_result 的占位符里带可追溯路径和字符数
# 设计：构造长文本调用，断言占位符同时包含 tool_outputs 路径和省略字符数信息
def test_placeholder_includes_path_and_omitted_size(tmp_path: Path) -> None:
    long_text = "y" * 12_345
    messages = [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": long_text}
    ]}]
    result = persist_and_truncate_tool_results(messages, tmp_path, limit=8_000)
    placeholder = result[0]["content"][0]["content"]
    assert "tool_outputs/" in placeholder
    assert "12345" in placeholder
    assert "chars omitted" in placeholder
