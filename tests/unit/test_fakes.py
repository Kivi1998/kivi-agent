"""tests/_fakes/ 共享 Mock 库的单元测试。

目的：
1. 验证每个 Fake 能用（基本 API 工作）
2. 验证 import 路径稳定（`from tests._fakes import FakeLlmProvider, ...`）
3. 验证关键设计：100% 离线（不导入 redis / httpx / anthropic 等）

不在这里测 Fake 的**业务行为**（那是单元测试的范围）—— 这里只做"骨架可用"验证。
"""
from __future__ import annotations

import pytest

from tests._fakes import (
    BusinessToolFixture,
    FakeEventBus,
    FakeLlmProvider,
    FakeSocketClient,
    LlmScriptedResponse,
    make_fixtures,
)
from tests._fakes.business_tools import (
    EChartsRenderFixture,
    MemoryRecallFixture,
    MemorySaveFixture,
    QueryDatabaseFixture,
    RagQueryFixture,
    WebSearchFixture,
)
from tests._fakes.event_bus import FaultMode

# ---- import 路径稳定 -------------------------------------------------------

# 功能：验证 tests._fakes 的对外 import 路径不漂移
# 设计：直接 import 并 assert isinstance，避免改名时静默破坏
def test_fakes_public_imports_resolve() -> None:
    assert FakeLlmProvider is not None
    assert FakeEventBus is not None
    assert FakeSocketClient is not None
    assert BusinessToolFixture is not None
    assert LlmScriptedResponse is not None
    assert make_fixtures is not None


# 功能：验证 tests._fakes 100% 离线——不依赖任何外部服务
# 设计：扫描 tests/_fakes/ 所有 .py 文件，禁止 import 任何外部网络/数据库包
def test_fakes_no_external_service_imports() -> None:
    forbidden = {
        "redis", "asyncpg", "psycopg2", "pymongo", "sqlalchemy",
        "langchain", "langgraph", "openai", "anthropic",
        "httpx", "aiohttp", "requests", "urllib3",
        "fastapi", "uvicorn", "starlette",
        "boto3", "kubernetes", "docker",
    }
    from pathlib import Path

    fakes_dir = Path(__file__).resolve().parents[1] / "_fakes"
    offenders: list[str] = []
    for py in fakes_dir.glob("*.py"):
        content = py.read_text(encoding="utf-8")
        for line_no, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith(("import ", "from ")):
                continue
            for dep in forbidden:
                # 允许在注释中讨论这些包；只检查实际 import
                if f"import {dep}" in stripped or f"from {dep}" in stripped:
                    offenders.append(
                        f"{py.name}:{line_no}: {stripped}"
                    )
    assert not offenders, (
        f"tests/_fakes/ 不应 import 外部服务: {offenders}\n"
        f"如必须依赖，请用 try/except 包装并降级（见 _fakes/__init__.py 设计）"
    )


# ---- FakeLlmProvider -------------------------------------------------------

# 功能：验证 FakeLlmProvider 在 echo 模式下能流式产出 LlmTokenEvent
# 设计：未配脚本时回 echo 用户最后一条消息；断言流切片按 chunk_size 推送
async def test_fake_llm_provider_echo_mode_publishes_tokens() -> None:
    bus = FakeEventBus()
    provider = FakeLlmProvider(model="fake-echo")

    response = await provider.chat(
        messages=[{"role": "user", "content": "hello world"}],
        tool_schemas=[],
        bus=bus,
        run_id="run-1",
        step=0,
    )

    assert response.text == "[echo] hello world"
    assert response.stop_reason == "end_turn"
    # 流式：1 token / event（chunk_size=1）
    assert bus.published_types["llm.token"] == len("hello world") + len("[echo] ")
    assert provider.call_count == 1
    assert provider.last_run_id == "run-1"


# 功能：验证 FakeLlmProvider 脚本模式按顺序消费
# 设计：构造 2 条脚本化响应，调用 2 次，验证第二次拿到第二条
async def test_fake_llm_provider_scripted_mode_sequential() -> None:
    bus = FakeEventBus()
    provider = FakeLlmProvider(
        scripted=[
            LlmScriptedResponse(text="first", input_tokens=5, output_tokens=1),
            LlmScriptedResponse(text="second", input_tokens=10, output_tokens=1),
        ]
    )

    r1 = await provider.chat(
        messages=[{"role": "user", "content": "q1"}],
        tool_schemas=[],
        bus=bus,
        run_id="run-1",
    )
    r2 = await provider.chat(
        messages=[{"role": "user", "content": "q2"}],
        tool_schemas=[],
        bus=bus,
        run_id="run-1",
    )
    assert r1.text == "first"
    assert r2.text == "second"
    # 第三次调用 → 脚本耗尽 → echo 模式
    r3 = await provider.chat(
        messages=[{"role": "user", "content": "q3"}],
        tool_schemas=[],
        bus=bus,
        run_id="run-1",
    )
    assert r3.text == "[echo] q3"


# 功能：验证 FakeLlmProvider 脚本化异常
# 设计：脚本里设 raise_exc，chat() 应原样抛出
async def test_fake_llm_provider_scripted_exception() -> None:
    bus = FakeEventBus()
    provider = FakeLlmProvider(
        scripted=[LlmScriptedResponse(raise_exc=RuntimeError("simulated"))]
    )

    with pytest.raises(RuntimeError, match="simulated"):
        await provider.chat(
            messages=[{"role": "user", "content": "q"}],
            tool_schemas=[],
            bus=bus,
            run_id="run-1",
        )


# 功能：验证 FakeLlmProvider.with_tool_call 工厂方法
# 设计：两段式响应（text + tool_use → end_turn）；断言 tool_calls 字段被填充
async def test_fake_llm_provider_with_tool_call_factory() -> None:
    bus = FakeEventBus()
    provider = FakeLlmProvider.with_tool_call(
        tool_name="web_search",
        tool_input={"query": "kivi"},
    )

    r1 = await provider.chat(
        messages=[{"role": "user", "content": "search kivi"}],
        tool_schemas=[],
        bus=bus,
        run_id="run-1",
    )
    assert r1.stop_reason == "tool_use"
    assert len(r1.tool_calls) == 1
    assert r1.tool_calls[0].name == "web_search"
    assert r1.tool_calls[0].input == {"query": "kivi"}


# ---- FakeEventBus ----------------------------------------------------------

# 功能：验证 FakeEventBus 记录事件快照与计数
# 设计：publish 2 次同一类型，断言 count == 2
async def test_fake_event_bus_records_events() -> None:
    from pydantic import BaseModel

    class _E(BaseModel):
        type: str = "test.event"
        value: int = 0

    bus = FakeEventBus()
    await bus.publish(_E(value=1))
    await bus.publish(_E(value=2))
    bus.assert_published("test.event", count=2)
    assert len(bus.events) == 2


# 功能：验证 FakeEventBus handler 异常在 LOG 模式下不传播
# 设计：handler 抛 RuntimeError，LOG 模式下 publish 应正常返回
async def test_fake_event_bus_fault_mode_log_does_not_propagate() -> None:
    from pydantic import BaseModel

    class _E(BaseModel):
        type: str = "test.event"

    bus = FakeEventBus(fault_mode=FaultMode.LOG)

    async def bad_handler(_: BaseModel) -> None:
        raise RuntimeError("boom")

    bus.subscribe(bad_handler)
    # 不应抛
    await bus.publish(_E())
    assert len(bus.handler_errors) == 1


# 功能：验证 FakeEventBus handler 异常在 RAISE 模式下传播
# 设计：与 LOG 模式对照，验证故障注入
async def test_fake_event_bus_fault_mode_raise_propagates() -> None:
    from pydantic import BaseModel

    class _E(BaseModel):
        type: str = "test.event"

    bus = FakeEventBus(fault_mode=FaultMode.RAISE)

    async def bad_handler(_: BaseModel) -> None:
        raise RuntimeError("boom")

    bus.subscribe(bad_handler)
    with pytest.raises(RuntimeError, match="boom"):
        await bus.publish(_E())


# ---- FakeSocketClient ------------------------------------------------------

# 功能：验证 FakeSocketClient 预设响应 + send_command
# 设计：set_response + send_command 应返回预设 dict
async def test_fake_socket_client_preset_response() -> None:
    client = FakeSocketClient(host="fake", port=0)
    await client.connect()
    client.set_response("ping", {"pong": True, "ts": "2026-07-22T10:00:00Z"})

    result = await client.send_command("ping", {})
    assert result == {"pong": True, "ts": "2026-07-22T10:00:00Z"}
    client.assert_called("ping", count=1)
    await client.close()
    assert client.close_count == 1


# 功能：验证 FakeSocketClient 推送事件到 handler
# 设计：注册 handler → push_event → handler 收到
async def test_fake_socket_client_push_event() -> None:
    client = FakeSocketClient()
    await client.connect()

    received: list[dict[str, object]] = []

    async def handler(event: dict[str, object]) -> None:
        received.append(event)

    client.on_event(handler)
    await client.push_event({"type": "core.started", "version": "0.0.1"})
    assert received == [{"type": "core.started", "version": "0.0.1"}]


# 功能：验证 FakeSocketClient 预设异常
# 设计：set_error 后 send_command 应抛该异常
async def test_fake_socket_client_preset_error() -> None:
    client = FakeSocketClient()
    await client.connect()
    client.set_error("bad", RuntimeError("simulated"))

    with pytest.raises(RuntimeError, match="simulated"):
        await client.send_command("bad", {})


# 功能：验证 FakeSocketClient 未预设 method 时报错
# 设计：fail-fast 而非静默返回 None/{}，避免测试假阳性
async def test_fake_socket_client_unpreset_method_raises() -> None:
    client = FakeSocketClient()
    await client.connect()

    with pytest.raises(KeyError, match="未预设"):
        await client.send_command("not_set", {})


# ---- business_tools fixture ------------------------------------------------

# 功能：验证 make_fixtures 返回的容器覆盖 v1 §1 全部 6 个 Tool 名
# 设计：断言 all_names 与契约字面值严格一致（顺序也一致，防止新增/删除漂移）
def test_business_tool_fixture_covers_all_v1_names() -> None:
    # v1 §1 锁定的 6 个业务 Tool 名（与 tests/contract/conftest.py 同源）
    expected = (
        "web_search",
        "rag_query",
        "query_database",
        "echarts_render",
        "memory_save",
        "memory_recall",
    )
    fixtures = make_fixtures()
    assert tuple(fixtures.all_names) == expected


# 功能：验证 web_search fixture 的 input/output 字段名稳定
# 设计：抓典型字段（query / top_k），避免 C 阶段改字段名
def test_web_search_fixture_schema() -> None:
    fx = WebSearchFixture()
    inp = fx.input()
    assert "query" in inp
    assert "top_k" in inp
    out = fx.output()
    assert "results" in out
    assert isinstance(out["results"], list)


# 功能：验证 rag_query fixture 的两阶段字段（rewritten + chunks + citations）
# 设计：v1 §1 锁定 `rag_query` 是合并后的接口，输出必须含全部三段
def test_rag_query_fixture_contains_rewrite_and_chunks() -> None:
    fx = RagQueryFixture()
    out = fx.output()
    assert "rewritten_query" in out
    assert "chunks" in out
    assert "citations" in out


# 功能：验证 echarts_render fixture 输出 ECharts option dict
# 设计：ECharts option 必有 xAxis/yAxis/series 三个核心键
def test_echarts_render_fixture_echarts_shape() -> None:
    fx = EChartsRenderFixture()
    out = fx.output()
    assert "xAxis" in out
    assert "yAxis" in out
    assert "series" in out


# 功能：验证 query_database fixture 含两阶段 SQL + row_count
# 设计：v1 §1 锁定 `query_database` 两阶段，输出必有 sql + columns + rows + row_count
def test_query_database_fixture_two_phase_output() -> None:
    fx = QueryDatabaseFixture()
    out = fx.output()
    for k in ("sql", "columns", "rows", "row_count"):
        assert k in out, f"query_database 输出缺 {k}"


# 功能：验证 memory_save / memory_recall fixture 字段稳定
# 设计：memory_recall 必须有 hit 字段（v1 评测指标需要 hit/miss 区分）
def test_memory_fixtures_have_required_fields() -> None:
    save_out = MemorySaveFixture().output()
    assert "memory_id" in save_out
    assert "content_hash" in save_out
    recall_out = MemoryRecallFixture().output()
    assert "results" in recall_out
    assert "hit" in recall_out
