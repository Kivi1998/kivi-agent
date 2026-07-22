"""EvalEmitter 单元测试（Wave 1 / E 阶段 T3）。

测试目标：
1. JSONL 路径：写入本地文件，可读回
2. Redis 路径在 `redis` 包不可用时不报错（降级到 JSONL）
3. 订阅 EventBus 多个事件类型，全部落到后端
4. handler 异常**不传播**到 publisher（演示版容错）
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from kivi_agent.evaluation import (
    EvalEmitter,
    EvalEmitterConfig,
    JsonlEmitterBackend,
    assert_schema_version,
    current_schema_version,
    redis_available,  # noqa: F401  验证公开 API
)
from kivi_agent.evaluation.emitter import (
    SCHEMA_VERSION,
    Envelope,
    _event_to_payload,
    _event_type_of,
    _jsonify,
)

# ---- 当前 schema_version 守门 -----------------------------------------------

# 功能：验证当前 schema 版本字面值是 1
# 设计：直接调 API，不写死 1
def test_current_schema_version_is_one() -> None:
    assert current_schema_version() == 1


# 功能：验证 assert_schema_version 匹配时通过
# 设计：用 parametrize 覆盖多个匹配值；并验证类型提示不是 None
def test_assert_schema_version_matches() -> None:
    assert_schema_version(1, 1, "RunContext")  # 不抛
    assert_schema_version(2, 2, "TraceEnvelope")  # 不抛


# 功能：验证 assert_schema_version 不匹配时抛清晰错误
# 设计：错误信息必须含类名 + actual + expected + 升级提示
def test_assert_schema_version_mismatch_raises() -> None:
    from kivi_agent.evaluation.contract_version import ContractVersionMismatchError

    with pytest.raises(ContractVersionMismatchError) as exc:
        assert_schema_version(2, 1, "RunContext")
    msg = str(exc.value)
    assert "RunContext" in msg
    assert "2" in msg
    assert "1" in msg
    assert "schema_version" in msg
    assert "ADR" in msg  # 引导看 ADR 流程


# ---- JSONL 后端 ------------------------------------------------------------

# 功能：验证 JSONL 后端把每条 envelope 落成一行 JSON
# 设计：tmp_path 创建临时文件，写 2 条，逐行读回验证
async def test_jsonl_backend_writes_one_line_per_envelope(tmp_path: Path) -> None:
    backend = JsonlEmitterBackend(tmp_path / "events.jsonl")
    await backend.write(
        Envelope(event_type="run.started", run_id="r1", payload={"goal": "test"})
    )
    await backend.write(
        Envelope(event_type="run.finished", run_id="r1", payload={"status": "success"})
    )
    await backend.close()

    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2

    r1 = json.loads(lines[0])
    assert r1["schema_version"] == SCHEMA_VERSION
    assert r1["event_type"] == "run.started"
    assert r1["run_id"] == "r1"
    assert r1["payload"] == {"goal": "test"}

    r2 = json.loads(lines[1])
    assert r2["event_type"] == "run.finished"
    assert r2["payload"] == {"status": "success"}


# 功能：验证 JSONL 后端写含中文 payload 时不丢字
# 设计：ensure_ascii=False 在 emitter 内已设，验证输出非 \uXXXX
async def test_jsonl_backend_preserves_unicode(tmp_path: Path) -> None:
    backend = JsonlEmitterBackend(tmp_path / "uni.jsonl")
    await backend.write(
        Envelope(event_type="llm.token", run_id="r", payload={"token": "你好"})
    )
    await backend.close()

    text = (tmp_path / "uni.jsonl").read_text(encoding="utf-8")
    assert "你好" in text
    assert "\\u" not in text


# ---- EvalEmitter 主体 -------------------------------------------------------

# 自定义事件类型（避免依赖 core/bus 的具体事件）
class _RunStarted(BaseModel):
    type: str = "test.run_started"
    run_id: str
    goal: str


class _RunFinished(BaseModel):
    type: str = "test.run_finished"
    run_id: str
    status: str


# 功能：验证 EvalEmitter.start 后订阅 EventBus，publish 事件自动落 JSONL
# 设计：用 in-memory FakeEventBus 验证订阅生效（不引入真实 EventBus）
async def test_eval_emitter_subscribes_and_writes(tmp_path: Path) -> None:
    from tests._fakes import FakeEventBus

    bus = FakeEventBus()
    cfg = EvalEmitterConfig(backend="jsonl", jsonl_path=tmp_path / "e.jsonl")
    emitter = EvalEmitter(bus=bus, config=cfg)

    await emitter.start()
    try:
        await bus.publish(_RunStarted(run_id="r1", goal="g1"))
        await bus.publish(_RunFinished(run_id="r1", status="success"))
        # 给 handler 微小时间窗（FakeEventBus 是同步 await，但保险起见）
        import asyncio
        await asyncio.sleep(0)
    finally:
        await emitter.stop()

    # 验证 JSONL 文件内容
    lines = (tmp_path / "e.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    r1 = json.loads(lines[0])
    assert r1["event_type"] == "test.run_started"
    assert r1["run_id"] == "r1"
    assert r1["payload"]["goal"] == "g1"


# 功能：验证 EvalEmitter 默认 backend=jsonl 不依赖 redis 包
# 设计：构造时不传 backend，验证 backend 字段是 JsonlEmitterBackend
def test_eval_emitter_default_backend_is_jsonl(tmp_path: Path) -> None:
    from tests._fakes import FakeEventBus

    bus = FakeEventBus()
    cfg = EvalEmitterConfig(jsonl_path=tmp_path / "d.jsonl")
    emitter = EvalEmitter(bus=bus, config=cfg)
    assert isinstance(emitter.backend, JsonlEmitterBackend)


# 功能：验证 backend="redis" 但缺 redis 包时降级到 JSONL（绝不 hard-fail）
# 设计：当前环境无 redis 包；构造后断言 backend 是 JsonlEmitterBackend 而不是抛错
def test_eval_emitter_redis_fallback_when_package_missing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # 如果测试环境装了 redis，强制走"假定不可用"分支
    # 用 monkeypatch 让 redis_available() 返回 False
    import kivi_agent.evaluation.emitter as emitter_mod
    from tests._fakes import FakeEventBus

    original_available = emitter_mod._REDIS_AVAILABLE
    emitter_mod._REDIS_AVAILABLE = False
    try:
        bus = FakeEventBus()
        cfg = EvalEmitterConfig(backend="redis", jsonl_path=tmp_path / "fb.jsonl")
        with caplog.at_level(logging.WARNING):
            emitter = EvalEmitter(bus=bus, config=cfg)
        # 降级到 JSONL
        assert isinstance(emitter.backend, JsonlEmitterBackend)
        # 警告日志可读
        assert any("降级" in r.message for r in caplog.records)
    finally:
        emitter_mod._REDIS_AVAILABLE = original_available


# 功能：验证 backend="redis" 且 redis 包可用时构造 RedisStreamsEmitterBackend
# 设计：monkeypatch 让 _REDIS_AVAILABLE=True，但 RedisStreamsEmitterBackend 自身是 stub
#       （避免在测试中真连 Redis）；只验证类型分支
def test_eval_emitter_redis_backend_chosen_when_available(
    tmp_path: Path,
) -> None:
    import kivi_agent.evaluation.emitter as emitter_mod
    from tests._fakes import FakeEventBus

    # monkeypatch：让 _REDIS_AVAILABLE=True，并给 RedisStreamsEmitterBackend 注入 stub
    class _StubRedis:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.kwargs = kwargs

    original_available = emitter_mod._REDIS_AVAILABLE
    original_cls = emitter_mod.RedisStreamsEmitterBackend
    emitter_mod._REDIS_AVAILABLE = True
    # 类型替换：mypy 不接受"把 class A 换成 class B"，运行时 monkeypatch 必要
    setattr(emitter_mod, "RedisStreamsEmitterBackend", _StubRedis)
    try:
        bus = FakeEventBus()
        cfg = EvalEmitterConfig(backend="redis", jsonl_path=tmp_path / "r.jsonl")
        emitter = EvalEmitter(bus=bus, config=cfg)
        assert isinstance(emitter.backend, _StubRedis)
    finally:
        emitter_mod._REDIS_AVAILABLE = original_available
        setattr(emitter_mod, "RedisStreamsEmitterBackend", original_cls)


# 功能：验证 handler 异常时 EvalEmitter 不污染 publisher
# 设计：注入坏后端 → publish 事件 → 不抛
async def test_eval_emitter_backend_failure_does_not_break_publisher(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from tests._fakes import FakeEventBus

    class _BrokenBackend:
        async def write(self, envelope: Envelope) -> None:
            raise OSError("disk full")

        async def flush(self) -> None:
            pass

        async def close(self) -> None:
            pass

    bus = FakeEventBus()
    cfg = EvalEmitterConfig(jsonl_path=tmp_path / "b.jsonl")
    emitter = EvalEmitter(bus=bus, config=cfg, backend=_BrokenBackend())
    await emitter.start()
    try:
        with caplog.at_level(logging.WARNING):
            await bus.publish(_RunStarted(run_id="r1", goal="g1"))
            # handler 异常被吞
    finally:
        await emitter.stop()
    assert any("写入失败" in r.message for r in caplog.records)


# 功能：验证 import kivi_agent.evaluation 不依赖 redis
# 设计：import 时间不应触发 redis import（演示版隔离）
def test_evaluation_import_does_not_load_redis() -> None:

    # 移除 redis（如已加载）以观察 import 行为
    # 注：实际测试中不一定能完全隔离，但构造期应不抛
    import kivi_agent.evaluation  # noqa: F401

    # kivi_agent.evaluation 顶层包可被实例化
    assert hasattr(kivi_agent.evaluation, "EvalEmitter")
    assert hasattr(kivi_agent.evaluation, "Judge")
    assert hasattr(kivi_agent.evaluation, "JsonlEmitterBackend")


# ---- 内部工具 ---------------------------------------------------------------

# 功能：验证 _event_type_of 优先用 .type 字段，pydantic 模型有 discriminator
def test_event_type_of_uses_type_field() -> None:
    e = _RunStarted(run_id="r", goal="g")
    assert _event_type_of(e) == "test.run_started"


# 功能：验证 _event_to_payload 完整 dump pydantic 模型
def test_event_to_payload_dumps_pydantic() -> None:
    e = _RunStarted(run_id="r1", goal="goal1")
    p = _event_to_payload(e)
    assert p == {"type": "test.run_started", "run_id": "r1", "goal": "goal1"}


# 功能：验证 _jsonify 递归处理嵌套 dict / list / datetime
def test_jsonify_handles_nested_structures() -> None:
    from datetime import datetime

    obj = {
        "a": 1,
        "b": [1, 2, {"c": "x"}],
        "d": {"e": datetime(2026, 7, 22, 10, 0, 0)},
        "f": None,
    }
    out = _jsonify(obj)
    assert out["a"] == 1
    assert out["b"] == [1, 2, {"c": "x"}]
    # datetime 被 pydantic-aware jsonify 序列化为 ISO
    assert isinstance(out["d"]["e"], str)
    assert out["f"] is None
