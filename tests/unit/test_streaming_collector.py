from __future__ import annotations

from kama_claude.core.llm.streaming import StreamAccumulator


# 功能：验证多个文本增量按顺序拼接成完整文本
# 设计：模拟流式返回的三个文本片段，断言 finalize 后拼接结果正确
def test_accumulator_joins_text_deltas() -> None:
    acc = StreamAccumulator()
    acc.add_content_delta("hel")
    acc.add_content_delta("lo")
    text, tool_calls = acc.finalize()
    assert text == "hello"
    assert tool_calls == []


# 功能：验证同一 index 的多个工具调用增量（id/name 各到一次、arguments 分片到达）能正确聚合成一个 ToolCallBlock
# 设计：这是 OpenAI 流式协议的真实行为——function.arguments 是逐字符/逐片段流式送达的 JSON 字符串，
#      必须按 index 累加而不是覆盖，覆盖这个核心聚合逻辑
def test_accumulator_aggregates_tool_call_by_index() -> None:
    acc = StreamAccumulator()
    acc.add_tool_call_delta(0, "call_1", "bash", '{"comm')
    acc.add_tool_call_delta(0, "", "", 'and": "ls"}')
    text, tool_calls = acc.finalize()
    assert len(tool_calls) == 1
    assert tool_calls[0].id == "call_1"
    assert tool_calls[0].name == "bash"
    assert tool_calls[0].input == {"command": "ls"}


# 功能：验证多个不同 index 的工具调用各自独立聚合，不会串到一起
# 设计：一次响应里模型并行发起两个工具调用是常见场景，覆盖多 tool_call 场景
def test_accumulator_handles_multiple_tool_calls() -> None:
    acc = StreamAccumulator()
    acc.add_tool_call_delta(0, "call_1", "read_file", '{"path": "a.py"}')
    acc.add_tool_call_delta(1, "call_2", "read_file", '{"path": "b.py"}')
    _, tool_calls = acc.finalize()
    assert len(tool_calls) == 2
    assert {tc.id for tc in tool_calls} == {"call_1", "call_2"}
