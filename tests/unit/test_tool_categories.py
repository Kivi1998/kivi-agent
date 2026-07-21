from __future__ import annotations

from kama_claude.core.tools.builtin.bash import BashTool
from kama_claude.core.tools.builtin.read_file import ReadFileTool
from kama_claude.core.tools.builtin.write_file import WriteFileTool


# 功能：验证只读类工具被标记为 category="read"
# 设计：直接读类属性而不实例化调用，因为分类是静态元数据，不依赖运行时状态
def test_read_only_tools_are_category_read() -> None:
    assert ReadFileTool.category == "read"


# 功能：验证会修改文件系统状态的工具被标记为 category="write"
# 设计：write_file 明确是写类工具，用它做代表性断言
def test_write_tools_are_category_write() -> None:
    assert WriteFileTool.category == "write"


# 功能：验证执行任意 shell 命令的工具被标记为 category="command"（语义上可读可写，单独归一类）
# 设计：bash 无法静态判断读写，归为独立的 "command" 类，供权限模式矩阵和并发判断区别对待
def test_bash_is_category_command() -> None:
    assert BashTool.category == "command"
