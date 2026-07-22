"""契约测试包（Wave 1 / E 阶段）。

契约测试不是单元测试的替代品，而是**接口边界的守门人**：
- 验证 `docs/contracts/v1.md` 中冻结的字段集、字段名、类型约束在代码实现里**真实存在**
- 任何 Agent 改动 RunContext / AgentProfile / BaseTool 字段时，CI 会失败
- 防止 B/E 阶段重新引入旧名（`search_knowledge_base` / `params_schema` 等）

设计原则：
1. **冒烟优先**：不验证行为细节，只验证"契约字段存在 + 命名正确"
2. **离线**：不依赖真实 LLM / Redis / Postgres
3. **可降级**：A/B/C/D 未完成时仍能跑（用协议期望或 TODO 标记）
4. **单一来源**：所有契约字面值引用 `docs/contracts/v1.md` 章节
"""
