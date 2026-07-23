"""tests/e2e 包：业务 Agent 端到端事件流断言（agent: package-events-bridge-v2）。

本目录下的 E2E 测试按 v1 §5 E2E 事件流断言要求，跑一个多意图 query
（"对比网上关于 RAG 的最新文章和我们内部知识库"）走完整业务链路，
断言事件流顺序与子 Agent 输出。

与 integration test 的区别：
- integration：调真实 daemon（free_port fixture + ANTHROPIC_API_KEY）
- e2e：mock LLM provider + 直接驱动 EventBus，验证业务事件流的契约
"""
