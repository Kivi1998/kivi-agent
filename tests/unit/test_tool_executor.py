from __future__ import annotations

from kama_claude.core.events.bus import EventBus
from kama_claude.core.llm.types import ToolCallBlock
from kama_claude.core.tools.executor import execute_tool_batches, partition_tool_calls
from kama_claude.core.tools.registry import ToolRegistry
from kama_claude.core.tools.builtin.read_file import ReadFileTool
from kama_claude.core.tools.builtin.write_file import WriteFileTool


# 功能：验证连续的只读工具调用被分进同一个 batch
# 设计：两个 read_file 调用相邻出现，断言 partition 结果是一个长度为 2 的 batch，而不是拆成两批
def test_consecutive_read_calls_share_one_batch() -> None:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    calls = [
        ToolCallBlock(id="1", name="read_file", input={"path": "a.py"}),
        ToolCallBlock(id="2", name="read_file", input={"path": "b.py"}),
    ]
    batches = partition_tool_calls(calls, registry)
    assert batches == [calls]


# 功能：验证只读工具和写工具混在一起时，写工具单独成批，不和只读工具并发
# 设计：read/write/read 三个调用，断言分成 [read] [write] [read] 三批而不是全部合并，
#      覆盖"遇到非只读工具就切新批次"这个核心分组规则
def test_write_call_breaks_batch() -> None:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    calls = [
        ToolCallBlock(id="1", name="read_file", input={"path": "a.py"}),
        ToolCallBlock(id="2", name="write_file", input={"path": "b.py", "content": "x"}),
        ToolCallBlock(id="3", name="read_file", input={"path": "c.py"}),
    ]
    batches = partition_tool_calls(calls, registry)
    assert len(batches) == 3
    assert [b[0].name for b in batches] == ["read_file", "write_file", "read_file"]


# 功能：验证未知工具名（registry 里查不到）被当作非只读处理，单独成批而不是崩溃
# 设计：工具名拼错或还没注册时，保守起见当成非并发安全，覆盖这个防御性分支
def test_unknown_tool_is_treated_as_non_concurrent() -> None:
    registry = ToolRegistry()
    calls = [ToolCallBlock(id="1", name="nonexistent_tool", input={})]
    batches = partition_tool_calls(calls, registry)
    assert batches == [calls]


# 功能：验证 execute_tool_batches 对每个 tool_call 都产出对应的 ToolResult，且顺序与输入一致
# 设计：两个 read_file 调用（会被分进同一并发批次），断言返回结果列表长度和顺序正确，
#      覆盖"并发执行不会打乱结果和原始调用的对应关系"这个关键正确性
async def test_execute_tool_batches_preserves_call_result_pairing(tmp_path) -> None:
    (tmp_path / "a.py").write_text("A")
    (tmp_path / "b.py").write_text("B")
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    calls = [
        ToolCallBlock(id="1", name="read_file", input={"path": str(tmp_path / "a.py")}),
        ToolCallBlock(id="2", name="read_file", input={"path": str(tmp_path / "b.py")}),
    ]
    batches = partition_tool_calls(calls, registry)
    pairs = await execute_tool_batches(batches, registry, EventBus(), run_id="r1")
    assert [tc.id for tc, _ in pairs] == ["1", "2"]
    assert pairs[0][1].content == "A"
    assert pairs[1][1].content == "B"
