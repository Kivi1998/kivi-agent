from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from kivi_agent.core.bus.commands import Command, SessionCancelCommand, SessionCancelResult


# 功能：SessionCancelCommand 序列化往返后字段完整保留
# 设计：构造带 session_id / reason 的实例，JSON 往返断言两字段值；
#      这是 v1 §5.2.2 SessionCancel 命令的字段契约
def test_session_cancel_command_roundtrip() -> None:
    cmd = SessionCancelCommand(session_id="sess-1", reason="user_requested")
    data = cmd.model_dump()
    assert data["type"] == "session.cancel"
    restored = SessionCancelCommand.model_validate(data)
    assert restored.session_id == "sess-1"
    assert restored.reason == "user_requested"


# 功能：SessionCancelCommand.type 默认值为 "session.cancel"
# 设计：type 是 Command union 的判别键，必须与 union 定义完全一致，
#      否则反序列化时路由到错误类型
def test_session_cancel_command_default_type() -> None:
    cmd = SessionCancelCommand(session_id="sess-1")
    assert cmd.type == "session.cancel"


# 功能：SessionCancelCommand 缺 session_id 时 pydantic 校验失败
# 设计：空 dict 触发校验失败；session_id 是必填字段，缺失不能进入 handler
def test_session_cancel_command_missing_session_id_raises() -> None:
    with pytest.raises(ValidationError):
        SessionCancelCommand.model_validate({})


# 功能：SessionCancelCommand.reason 是可选字段，默认空字符串
# 设计：仅传 session_id 构造，断言 reason == ""；
#      reason 可空让最小调用（"取消就好"）成为可能
def test_session_cancel_command_reason_default_empty() -> None:
    cmd = SessionCancelCommand(session_id="sess-1")
    assert cmd.reason == ""


# 功能：SessionCancelResult 序列化往返后字段完整保留（含 cancelled bool / ts）
# 设计：构造 cancelled=True 与 cancelled=False 两种实例分别断言；
#      cancelled 是核心返回值，false 表示"无 run 在跑、取消无操作"
def test_session_cancel_result_roundtrip() -> None:
    ok = SessionCancelResult(session_id="sess-1", cancelled=True, ts="2026-01-01T00:00:00Z")
    data = ok.model_dump()
    restored = SessionCancelResult.model_validate(data)
    assert restored.session_id == "sess-1"
    assert restored.cancelled is True
    assert restored.ts == "2026-01-01T00:00:00Z"

    noop = SessionCancelResult(session_id="sess-1", cancelled=False, ts="2026-01-01T00:00:00Z")
    assert noop.cancelled is False


# 功能：SessionCancelCommand 能被 Command 判别联合正确反序列化
# 设计：用 TypeAdapter(Command) 把 dump 后的 dict 反序列化回 union，
#      断言 round-trip 后类型一致；这是 IPC 协议路由的基础
def test_command_union_recognizes_session_cancel() -> None:
    adapter = TypeAdapter(Command)
    cmd = SessionCancelCommand(session_id="sess-1", reason="user_requested")
    dumped = cmd.model_dump()
    restored = adapter.validate_python(dumped)
    assert type(restored) is SessionCancelCommand
    assert restored.model_dump() == dumped
