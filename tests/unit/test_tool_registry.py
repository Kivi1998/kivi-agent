from __future__ import annotations

from kama_claude.core.tools.base import BaseTool, ToolResult
from kama_claude.core.tools.builtin.read_file import ReadFileTool
from kama_claude.core.tools.builtin.write_file import WriteFileTool
from kama_claude.core.tools.registry import ToolRegistry


class _FakeTool(BaseTool):
    name = "fake"
    description = "A fake tool"
    input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

    async def invoke(self, params: dict[str, object]) -> ToolResult:
        return ToolResult(content="ok")


# 功能：验证注册工具后能通过名称检索到同一实例
# 设计：断言 `is`（同一对象引用）而非 `==`，确认 registry 存储的是引用而非副本，避免不必要的对象复制
def test_register_and_get() -> None:
    registry = ToolRegistry()
    tool = _FakeTool()
    registry.register(tool)
    assert registry.get("fake") is tool


# 功能：验证查询不存在的工具名返回 None 而非抛出异常
# 设计：空 registry 直接查询，确认返回值语义为 None（而非 KeyError），invoke_tool 依赖此行为判断"未知工具"
def test_get_unknown_returns_none() -> None:
    assert ToolRegistry().get("missing") is None


# 功能：验证 tool_schemas() 输出的每条记录包含 Anthropic API 所需的三个必填字段
# 设计：这三个字段（name/description/input_schema）是 Anthropic tool definition 格式，缺少任何一个都会导致 LLM 调用失败
def test_tool_schemas_contains_name_description_input_schema() -> None:
    registry = ToolRegistry()
    registry.register(_FakeTool())
    schemas = registry.tool_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "fake"
    assert schemas[0]["description"] == "A fake tool"
    assert "input_schema" in schemas[0]


# 功能：验证多工具注册后 tool_schemas() 包含所有工具，不遗漏
# 设计：用 set 比较名称集合而非检查顺序，聚焦"完整性"而非"顺序"，确认 registry 不遗漏任何已注册工具
def test_multiple_tools_all_appear_in_schemas() -> None:
    class _AnotherTool(BaseTool):
        name = "another"
        description = "Another"
        input_schema: dict[str, object] = {"type": "object", "properties": {}, "required": []}

        async def invoke(self, params: dict[str, object]) -> ToolResult:
            return ToolResult(content="")

    registry = ToolRegistry()
    registry.register(_FakeTool())
    registry.register(_AnotherTool())
    names = {s["name"] for s in registry.tool_schemas()}
    assert names == {"fake", "another"}


# 功能：验证重复注册同名工具时新版本覆盖旧版本（覆盖语义而非追加）
# 设计：检查 description 变更，确认 registry 的覆盖语义，防止工具版本冲突导致旧实现残留
def test_register_same_name_overwrites() -> None:
    class _Updated(BaseTool):
        name = "fake"
        description = "updated"
        input_schema: dict[str, object] = {}

        async def invoke(self, params: dict[str, object]) -> ToolResult:
            return ToolResult(content="")

    registry = ToolRegistry()
    registry.register(_FakeTool())
    registry.register(_Updated())
    found = registry.get("fake")
    assert found is not None
    assert found.description == "updated"


# 功能：验证 deferred=True 注册的工具默认不出现在 tool_schemas() 里
# 设计：这是"按需暴露"的核心行为——工具存在于 registry（get() 能查到），但不会被推给 LLM，
#      除非被 mark_discovered 过
def test_deferred_tool_hidden_from_schemas_until_discovered() -> None:
    registry = ToolRegistry()
    registry.register(WriteFileTool(), deferred=True)
    names = {s["name"] for s in registry.tool_schemas()}
    assert "write_file" not in names
    assert registry.get("write_file") is not None  # 仍然可以被直接调用（比如工具搜索到之后）


# 功能：验证 mark_discovered 之后，该工具出现在 tool_schemas() 里
# 设计：覆盖"发现后才暴露"这个状态迁移
def test_marking_discovered_exposes_schema() -> None:
    registry = ToolRegistry()
    registry.register(WriteFileTool(), deferred=True)
    registry.mark_discovered("write_file")
    names = {s["name"] for s in registry.tool_schemas()}
    assert "write_file" in names


# 功能：验证非 deferred（默认）注册的工具始终暴露，不受这套机制影响
# 设计：确保新增的 deferred 参数不改变现有工具（大多数都是默认注册）的既有行为
def test_non_deferred_tool_always_visible() -> None:
    registry = ToolRegistry()
    registry.register(ReadFileTool())
    names = {s["name"] for s in registry.tool_schemas()}
    assert "read_file" in names


# 功能：验证 search 按名字/描述关键词打分，名字命中排名优先于描述命中
# 设计：复用包 G 的 SkillLoader.search 同款打分逻辑，覆盖基本检索正确性
def test_registry_search_finds_by_keyword() -> None:
    registry = ToolRegistry()
    registry.register(ReadFileTool(), deferred=True)
    registry.register(WriteFileTool(), deferred=True)
    results = registry.search("write")
    assert len(results) == 1
    assert results[0].name == "write_file"
