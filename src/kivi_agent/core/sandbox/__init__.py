from __future__ import annotations

import platform
from typing import Protocol


class Sandbox(Protocol):
    def wrap(self, command: str, *, allow_write: list[str], network: bool = False) -> str: ...


# 按当前操作系统选择沙箱实现；不支持的平台返回 None（调用方应回退为不沙箱执行并给出警告）
def create_sandbox() -> Sandbox | None:
    system = platform.system()
    if system == "Darwin":
        from kivi_agent.core.sandbox.seatbelt import SeatbeltSandbox
        return SeatbeltSandbox()
    if system == "Linux":
        from kivi_agent.core.sandbox.bwrap import BwrapSandbox
        return BwrapSandbox()
    return None
