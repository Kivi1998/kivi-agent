from __future__ import annotations

from kama_claude.core.sandbox.bwrap import BwrapSandbox
from kama_claude.core.sandbox.seatbelt import SeatbeltSandbox


# 功能：验证 SeatbeltSandbox.wrap 生成的命令以 sandbox-exec 开头并内嵌原始命令
# 设计：只校验拼装出的字符串结构（不实际执行），因为单元测试环境不一定是 macOS
def test_seatbelt_wrap_builds_sandbox_exec_command() -> None:
    sb = SeatbeltSandbox()
    wrapped = sb.wrap("echo hi", allow_write=["/tmp/work"], network=False)
    assert wrapped.startswith("/usr/bin/sandbox-exec")
    assert "echo hi" in wrapped
    assert "/tmp/work" in wrapped


# 功能：验证 network=True 时 Seatbelt profile 里包含允许网络的规则，network=False 时不包含
# 设计：分别用两种取值调用，断言 profile 文本里 "allow network*" 的出现与否，覆盖网络隔离开关
def test_seatbelt_network_toggle() -> None:
    sb = SeatbeltSandbox()
    with_net = sb.wrap("curl x", allow_write=[], network=True)
    without_net = sb.wrap("curl x", allow_write=[], network=False)
    assert "allow network*" in with_net
    assert "allow network*" not in without_net


# 功能：验证 BwrapSandbox.wrap 生成的命令以 bwrap 开头，且对 allow_write 路径加了可写 bind
# 设计：校验命令行参数片段而非真实执行，覆盖只读根 + 可写目录 bind 的核心逻辑
def test_bwrap_wrap_builds_bind_mounts() -> None:
    sb = BwrapSandbox()
    wrapped = sb.wrap("echo hi", allow_write=["/tmp/work"], network=False)
    assert wrapped.startswith("bwrap")
    assert "--bind /tmp/work /tmp/work" in wrapped
    assert "--unshare-net" in wrapped
    assert "echo hi" in wrapped
