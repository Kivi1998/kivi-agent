"""WT-E1: GatewayEventBridge 单元测试（agent: package-web-gateway-v3）。

设计：
- 用 FakeEventBus + fake WSBridge 验证 6 类业务事件被正确路由
- 覆盖所有 v1 §5.2.1 事件 + 非业务事件过滤 + 重复 start 幂等 + stop 后 no-op
- 验证 dispatched_count 计数 + ws_bridge.publish 收到正确 dict
"""

from __future__ import annotations

from typing import Any

from kivi_agent.core.bus.events import (
    ChartRenderedEvent,
    FrontendToolCallRequested,
    FrontendToolCallResponded,
    LlmThinkingEvent,
    RagSourcesCitedEvent,
    RunCancelledEvent,
)
from kivi_agent.gateway.event_bridge import GatewayEventBridge
from tests._fakes.event_bus import FakeEventBus


class _FakeWSBridge:
    """记录所有 publish 调用的 WSBridge fake。"""

    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []
        # 模拟 publish 抛异常的开关（测试容错）
        self.raise_on_publish: bool = False

    async def publish(self, event: dict[str, Any]) -> None:
        if self.raise_on_publish:
            raise RuntimeError("simulated bridge failure")
        self.published.append(event)


# 功能：6 类 v1 业务事件都被路由到 WSBridge.publish
# 设计：发 6 类事件各 1 条，断言 ws_bridge.published 收到 6 条 + dispatched_count == 6；
#      这是 v1 §5.2.1 契约"业务事件必须推 WS"的端到端验证
async def test_bridge_routes_all_six_v1_business_events() -> None:
    bus = FakeEventBus()
    bridge = _FakeWSBridge()
    gw_bridge = GatewayEventBridge(bus=bus, ws_bridge=bridge)  # type: ignore[arg-type]
    gw_bridge.start()

    run_id = "r-1"
    await bus.publish(LlmThinkingEvent(run_id=run_id, step=1, content="think", ts="t1"))
    await bus.publish(
        ChartRenderedEvent(
            run_id=run_id, chart_id="c1", option_dict={}, ts="t2"
        )
    )
    await bus.publish(
        RagSourcesCitedEvent(run_id=run_id, sources=[{"id": "s1"}], ts="t3")
    )
    await bus.publish(
        FrontendToolCallRequested(
            run_id=run_id, request_id="q1", tool_name="t1", args={}, ts="t4"
        )
    )
    await bus.publish(
        FrontendToolCallResponded(
            run_id=run_id, request_id="q1", result={"ok": True}, ts="t5"
        )
    )
    await bus.publish(RunCancelledEvent(run_id=run_id, reason="user", ts="t6"))

    assert gw_bridge.dispatched_count == 6
    assert len(bridge.published) == 6
    # 顺序与发布顺序一致
    assert bridge.published[0]["type"] == "llm.thinking"
    assert bridge.published[1]["type"] == "chart.rendered"
    assert bridge.published[2]["type"] == "rag.sources_cited"
    assert bridge.published[3]["type"] == "frontend.tool_call_requested"
    assert bridge.published[4]["type"] == "frontend.tool_call_responded"
    assert bridge.published[5]["type"] == "run.cancelled"
    # 关键字段保留
    assert bridge.published[0]["content"] == "think"
    assert bridge.published[1]["chart_id"] == "c1"
    assert bridge.published[2]["sources"] == [{"id": "s1"}]
    assert bridge.published[5]["reason"] == "user"


# 功能：非 v1 业务事件（RunStartedEvent 等）不被路由，避免污染 WS
# 设计：混入 RunStartedEvent，断言 ws_bridge 只收到 1 条 LlmThinkingEvent；
#      这是 6 事件过滤语义的关键保证（其他类型事件不应进 WS）
async def test_bridge_filters_non_business_events() -> None:
    from pydantic import BaseModel

    class _OtherEvent(BaseModel):
        type: str = "run.started"
        run_id: str = "r-1"
        goal: str = "g"
        ts: str = "t1"

    bus = FakeEventBus()
    bridge = _FakeWSBridge()
    gw_bridge = GatewayEventBridge(bus=bus, ws_bridge=bridge)  # type: ignore[arg-type]
    gw_bridge.start()

    await bus.publish(_OtherEvent())
    await bus.publish(LlmThinkingEvent(run_id="r-1", step=1, content="x", ts="t2"))

    assert gw_bridge.dispatched_count == 1
    assert len(bridge.published) == 1
    assert bridge.published[0]["type"] == "llm.thinking"


# 功能：事件没有 run_id 字段时被丢弃（防御性：避免空 run_id 污染 WS）
# 设计：构造一个伪造的 6 类事件变体（无 run_id），断言不被路由
async def test_bridge_drops_events_without_run_id() -> None:
    from pydantic import BaseModel

    class _FakeThinking(BaseModel):
        # 模拟 LlmThinkingEvent 但缺 run_id
        type: str = "llm.thinking"
        step: int = 1
        content: str = "x"
        ts: str = "t1"

    bus = FakeEventBus()
    bridge = _FakeWSBridge()
    gw_bridge = GatewayEventBridge(bus=bus, ws_bridge=bridge)  # type: ignore[arg-type]
    gw_bridge.start()

    await bus.publish(_FakeThinking())

    assert gw_bridge.dispatched_count == 0
    assert len(bridge.published) == 0


# 功能：start() 重复调用幂等（不会重复订阅）
# 设计：调 start() 2 次，断言 EventBus 只注册了 1 个 handler
def test_bridge_start_is_idempotent() -> None:
    bus = FakeEventBus()
    bridge = _FakeWSBridge()
    gw_bridge = GatewayEventBridge(bus=bus, ws_bridge=bridge)  # type: ignore[arg-type]
    gw_bridge.start()
    gw_bridge.start()
    assert bus.subscriber_count == 1


# 功能：stop() 后 _on_event 不再处理事件（dispatched_count 不变）
# 设计：发 1 条事件 → start → 发第 2 条 → stop → 发第 3 条；断言只有 2 条被路由
async def test_bridge_stop_disables_dispatch() -> None:
    bus = FakeEventBus()
    bridge = _FakeWSBridge()
    gw_bridge = GatewayEventBridge(bus=bus, ws_bridge=bridge)  # type: ignore[arg-type]

    await bus.publish(LlmThinkingEvent(run_id="r-1", step=1, content="pre", ts="t1"))
    assert gw_bridge.dispatched_count == 0  # 启动前 no-op

    gw_bridge.start()
    await bus.publish(LlmThinkingEvent(run_id="r-1", step=2, content="on", ts="t2"))
    assert gw_bridge.dispatched_count == 1

    gw_bridge.stop()
    await bus.publish(LlmThinkingEvent(run_id="r-1", step=3, content="off", ts="t3"))
    assert gw_bridge.dispatched_count == 1  # 停止后不再 dispatch


# 功能：ws_bridge.publish 抛异常时不影响 bus 流程（隔离错误）
# 设计：bridge 模拟 publish 抛 RuntimeError，断言 bus 流程继续且 dispatched_count 不变
async def test_bridge_isolates_publish_failure() -> None:
    bus = FakeEventBus()
    bridge = _FakeWSBridge()
    bridge.raise_on_publish = True
    gw_bridge = GatewayEventBridge(bus=bus, ws_bridge=bridge)  # type: ignore[arg-type]
    gw_bridge.start()

    # 不应抛错
    await bus.publish(LlmThinkingEvent(run_id="r-1", step=1, content="x", ts="t1"))
    # dispatched_count 仅在 publish 成功时递增；本次失败所以仍为 0
    assert gw_bridge.dispatched_count == 0
    # 后续事件仍能处理（bus 流程不被打断）
    bridge.raise_on_publish = False
    await bus.publish(LlmThinkingEvent(run_id="r-1", step=2, content="y", ts="t2"))
    assert gw_bridge.dispatched_count == 1
