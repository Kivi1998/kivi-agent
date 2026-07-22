"""共享 Mock / Fake 库（Wave 1 / E 阶段）。

设计目标：
1. **离线优先**：所有 Fake 100% 离线，CI 不需要任何外部服务
2. **可观察**：FakeEventBus / FakeLlmProvider 都暴露内部状态便于断言
3. **类型安全**：用 Protocol 标注接口契约，与生产代码保持一致
4. **可重置**：每个 Fake 都有 reset() 方法，跨测试隔离

何时用：
- 业务 Tool / Agent 单元测试需要 LLM 替身时 → `FakeLlmProvider`
- 事件发布/订阅单元测试时 → `FakeEventBus`
- IPC 客户端/服务端单元测试时 → `FakeSocketClient`
- 业务 Tool（web_search / rag_query / 等）的 fixture → `business_tools.py`

何时**不要**用：
- 集成测试需要真实 daemon → `tests/integration/conftest.py::running_daemon`
- 需要真实 LLM 行为 → `tests/integration/test_run_e2e.py`
"""
from tests._fakes.business_tools import (
    BusinessToolFixture,
    make_fixtures,
)
from tests._fakes.event_bus import FakeEventBus
from tests._fakes.llm import FakeLlmProvider, LlmScriptedResponse
from tests._fakes.socket_client import FakeSocketClient

__all__ = [
    "BusinessToolFixture",
    "FakeEventBus",
    "FakeLlmProvider",
    "FakeSocketClient",
    "LlmScriptedResponse",
    "make_fixtures",
]
