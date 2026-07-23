"""Demo 1 fixture：故意写错的 add 函数（agent: package-demo-v7）。

# demo1_buggy_add.py（agent: package-demo-v7）
初始 `add` 实现里把 `+` 错写成 `-`（经典 bug）。CodingAgent 需要 1+ 轮修复 + pytest 通过。
"""


def add(a: int, b: int) -> int:
    """返回 a + b（**故意**写成减法，触发 coding agent 修复）。"""
    return a - b
