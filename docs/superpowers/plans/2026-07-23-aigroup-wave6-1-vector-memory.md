# aigroup Wave 6.1：阶段 6 长期记忆 + 向量检索（ES + OpenAI Embedding）

> **基线**：`main @ a437565`（aigroup Wave 5.2 收官，1232 passed / 221 files / T11 + T12）
> **日期**：2026-07-23
> **承接关系**：Wave 1 已实现 `MemoryBackend` Protocol（write/read/search/update/delete/audit）+ `LocalMemoryBackend`（基于 Markdown）；阶段 6 主要缺**VectorMemoryBackend + 真实 Embedding + 语义召回 + 前端记忆管理 UI**。
> **用户决定（2026-07-23）**：
>   1. **只做阶段 6**（Vector Memory）；阶段 8（演示收口）推迟到 Wave 7
>   2. Vector 存储 = **Elasticsearch**（企业级）
>   3. Embedding = **OpenAI 兼容 Embedding API**（需 key，复用 `ANTHROPIC_BASE_URL` 思路）

---

## 一、目标

按整合方案阶段 6 的 12 项任务 + 4 项验收标准，从"本地 Markdown 记忆"升级为"向量检索 + 审计 + 语义去重"：

```
现有（Wave 1）
  LocalMemoryBackend（Markdown 文件 + 关键词匹配）
  MemoryBackend Protocol（write/read/search/update/delete/audit）
新增（Wave 6.1）
  VectorMemoryBackend（ES 8.x + knn 向量检索）
  EmbeddingProvider（OpenAI 兼容 API）
  Reranker（BM25 简单版，Wave 7 升 Cross-Encoder）
  敏感信息过滤（密码 / API key / token）
  语义去重（cosine > 0.95 合并）
  冲突归档（同时存在版本）
  记忆提取失败 fallback
  按问题召回 top_k（不再全注入上下文）
  前端记忆管理 UI
  Gateway 记忆 API
```

**核心交付**：
- VectorMemoryBackend（ES 实现）+ EmbeddingProvider
- 6 项记忆增强（类型 / 重要度 / 状态 / 过期 / 敏感信息 / 去重 / 审计）
- 7 个 Gateway 端点
- 前端 1 新视图（Memory 管理）
- 演示数据集 + 集成 + 文档

---

## 二、范围

### 2.1 必做（Wave 6.1 范围）

| 序号 | 任务 | 估时 | 交付 |
|---|---|---|---|
| J1 | VectorMemoryBackend（ES）+ EmbeddingProvider | 3-4 天 | `src/kivi_agent/core/memory/vector_backend.py` + `embedding/` + tests |
| J2 | 记忆增强（敏感 / 去重 / 冲突 / 审计 / fallback） | 2-3 天 | `src/kivi_agent/core/memory/{filter,dedup,audit,fallback}.py` + tests |
| J3 | Gateway 记忆 API（7 端点） | 2 天 | `src/kivi_agent/gateway/memory_dashboard.py` + tests |
| J4 | 前端记忆管理 UI | 2-3 天 | `apps/web-chat/src/{api,components,views}/Memory*` + 路由 + tests |
| 主控 | 演示 + 文档 + 集成 + ES docker-compose | 1-2 天 | 集成 commit + `docs/memory-demos/` + 收口记录 |

**总估时**：10-14 天，4 WT 并行 + 集成

### 2.2 阶段 6 任务列表 vs 实际拆分

整合方案阶段 6 12 项任务：

| 任务 | 状态 | 拆分到哪个 WT |
|---|---|---|
| ✅ 提炼 MemoryBackend 接口 | Wave 1 已做 | - |
| ✅ LocalMemoryBackend | Wave 1 已做 | - |
| ❌ 新增 VectorMemoryBackend | **J1** | J1 backend |
| ✅ 选 ES vs pgvector | 用户定 ES | J1 docker-compose |
| ❌ 迁移 Embedding / 召回 / Reranker | **J1** | J1 backend |
| ❌ 记忆类型 / 重要度 / 状态 / 过期 | **J2** | J2 增强 |
| ❌ 敏感信息过滤 | **J2** | J2 增强 |
| ❌ 语义去重 / 冲突归档 | **J2** | J2 增强 |
| ❌ 记忆审计事件 | **J2** | J2 增强（MemoryAuditEvent 已有） |
| ❌ 按问题召回（不再全注入） | **J1** | J1 search top_k |
| ❌ Markdown 导入/导出/编辑 | **J3** | J3 API（用户通过 API 编辑） |
| ❌ 对话压缩与长期记忆的边界测试 | **J2** | J2 测试 |

### 2.3 验收标准 vs 实际

| 验收 | 拆到哪个 WT 验证 |
|---|---|
| 小型本地模式不依赖外部数据库也能运行 | LocalMemoryBackend 保留，J1 默认 fallback 到 Local |
| 启用向量模式后只注入相关记忆 | J1 search(top_k=5) |
| 用户能查看/编辑/归档/删除记忆 | J3 API + J4 UI |
| 记忆提取失败不影响主任务 | J2 fallback 路径 |

---

## 三、4 个 WT 详细设计

### WT-J1: VectorMemoryBackend（ES）+ EmbeddingProvider

**目标**：实现 ES 向量检索后端 + OpenAI Embedding 客户端，按 query 召回 top_k

**代码位置**：
- `src/kivi_agent/core/memory/embedding/__init__.py`
- `src/kivi_agent/core/memory/embedding/protocol.py`：`EmbeddingProvider` Protocol（`async embed(texts: list[str]) -> list[list[float]]`）
- `src/kivi_agent/core/memory/embedding/openai_compat.py`：`OpenAICompatEmbedding`（调用 `${ANTHROPIC_BASE_URL}/v1/embeddings` 或 `${OPENAI_BASE_URL}/v1/embeddings`）
- `src/kivi_agent/core/memory/embedding/fake.py`：`FakeEmbedding`（hash 映射 384 维，演示用，单测用）
- `src/kivi_agent/core/memory/vector_backend.py`：`VectorMemoryBackend` 实现 `MemoryBackend` Protocol
  - 索引名：`kivi-memories`，mapping 含 `content` text + `embedding` knn_vector (dims=384) + `memory_type` keyword + `importance` float + `status` keyword + `created_at` date + `expires_at` date
  - 客户端用 `elasticsearch[async]>=8.0`
  - 失败 fallback 到 LocalMemoryBackend
- `src/kivi_agent/core/memory/rerank.py`：`BM25Reranker`（简单版，TF-IDF + cosine，Wave 7 升 Cross-Encoder）
- `src/kivi_agent/core/memory/__init__.py`：导出

**配置**：
- `RuntimeConfig.memory_backend`: `"local"` | `"vector"` (默认 `"local"`)
- `RuntimeConfig.embedding_provider`: `"fake"` | `"openai"` (默认 `"fake"`)
- `RuntimeConfig.embedding_dims`: int (默认 384)
- `RuntimeConfig.es_url`: str
- `RuntimeConfig.es_api_key`: str
- `RuntimeConfig.openai_base_url`: str（与 LLM 共享 `ANTHROPIC_BASE_URL`）
- `RuntimeConfig.openai_api_key`: str
- `RuntimeConfig.embedding_model`: str (默认 `text-embedding-3-small`)

**docker-compose**：
- `docker-compose.yml`（不是 `docker-compose.test.yml`）新加 `elasticsearch` service（ES 8.x，1GB heap，单节点）

**测试**：
- `tests/unit/test_embedding.py`（10+ case：fake / openai_compat 协议）
- `tests/unit/test_vector_backend.py`（15+ case：write/read/search/update/delete/audit/fallback）
- `tests/unit/test_rerank.py`（5+ case：BM25 基本行为）
- `tests/integration/test_vector_backend_e2e.py`（需要 ES Docker，可选）

**commit 规划**：5-6 commit
1. `feat(memory): EmbeddingProvider Protocol + FakeEmbedding + OpenAICompatEmbedding`
2. `feat(memory): BM25Reranker（简单版）`
3. `feat(memory): VectorMemoryBackend（ES 8.x + knn + fallback 到 Local）`
4. `test(memory): 30+ 单元测试 + ES e2e 测试（如可启）`
5. `chore(config): RuntimeConfig 加 memory_backend / embedding 配置项`
6. `fix(memory): 集成期 mypy 收尾（如需）`

### WT-J2: 记忆增强（敏感 / 去重 / 冲突 / 审计 / fallback）

**目标**：在 J1 基础上加 6 项记忆增强

**代码位置**：
- `src/kivi_agent/core/memory/filter.py`：`SensitiveInfoFilter`（正则：`(?i)(password|api_key|token|secret|private_key)\s*[:=]\s*\S+`）
- `src/kivi_agent/core/memory/dedup.py`：`SemanticDeduplicator`（cosine > 0.95 合并）
- `src/kivi_agent/core/memory/audit.py`：`MemoryAuditLogger`（MemoryAuditEvent 已有，加落盘 + 查询 API）
- `src/kivi_agent/core/memory/expire.py`：`MemoryExpiryPolicy`（按 expires_at 自动 archive）
- `src/kivi_agent/core/memory/fallback.py`：`MemoryExtractionFallback`（异常时记录 warning，返回原始消息，主任务继续）
- `src/kivi_agent/core/memory/types.py`：`MemoryType` Literal（user / feedback / project / reference / task）
- `src/kivi_agent/core/memory/lifecycle.py`：`MemoryLifecycle`（orchestrate：filter → dedup → write → audit → expire）

**MemoryItem 字段扩展**（已存在，确认）：
- `memory_type`: user / feedback / project / reference / task
- `importance`: 0.0-1.0（提取时由 LLM 评分）
- `status`: active / pending / archived / expired
- `created_at`: ISO 8601
- `expires_at`: ISO 8601 | None
- `source`: str（来源 session_id / tool_call_id）

**测试**：
- `tests/unit/test_filter.py`（10+ case：密码 / api_key / token / 中文 / 边界）
- `tests/unit/test_dedup.py`（8+ case：cosine 0.95 边界 / 多条 / 跨 session）
- `tests/unit/test_audit.py`（6+ case：写入 / 查询 / 时序）
- `tests/unit/test_expire.py`（5+ case：自动 archive / 手动 archive）
- `tests/unit/test_fallback.py`（6+ case：ES 不可用 / 解析失败 / 写失败）
- `tests/unit/test_lifecycle.py`（8+ case：filter→dedup→write→audit 链）
- `tests/integration/test_memory_lifecycle.py`（5+ case：端到端）

**commit 规划**：5-6 commit
1. `feat(memory): MemoryType Literal + MemoryItem 字段校验`
2. `feat(memory): SensitiveInfoFilter（正则密码 / api_key / token）`
3. `feat(memory): SemanticDeduplicator（cosine 0.95 合并）`
4. `feat(memory): MemoryAuditLogger（JSONL 落盘 + 查询 API）+ ExpiryPolicy`
5. `feat(memory): MemoryLifecycle 编排（filter→dedup→write→audit→expire）`
6. `test(memory): 50+ 单元测试 + 5+ 集成测试`

### WT-J3: Gateway 记忆 API（7 端点）

**目标**：复用 Wave 5.1 dashboard 模式，加 7 个记忆管理端点

**代码位置**：
- `src/kivi_agent/gateway/memory_dashboard.py`：7 端点
  - `GET /api/memory/items`（列表，按 status / memory_type 过滤）
  - `GET /api/memory/items/{id}`（单条）
  - `POST /api/memory/items`（手动创建）
  - `PATCH /api/memory/items/{id}`（更新内容/字段）
  - `DELETE /api/memory/items/{id}`（删除）
  - `POST /api/memory/items/{id}/archive`（归档）
  - `GET /api/memory/search?q=...&top_k=5`（向量检索）
  - `GET /api/memory/audit?memory_id=...`（审计历史）
- `src/kivi_agent/gateway/main.py`：挂载新 router（anchor comment block）
- `src/kivi_agent/core/memory/store.py`：加 `MemoryItemStore`（统一 Local / Vector 入口，typed 返回）

**测试**：
- `tests/unit/test_memory_dashboard_api.py`（7 端点 × 2 场景 = 14 case）
- `tests/integration/test_memory_dashboard_e2e.py`（5+ case：Local + Vector mock 双路径）

**commit 规划**：3-4 commit
1. `feat(memory): MemoryItemStore（统一 Local/Vector 入口）`
2. `feat(gateway): memory_dashboard 7 端点 + main.py 挂载`
3. `test(dashboard): memory 端点单测 + 集成测试`
4. `fix(gateway): 集成期 mypy 收尾（如需）`

### WT-J4: 前端记忆管理 UI

**目标**：Vue 3 + 1 新视图 + 1 路由

**代码位置**：
- `apps/web-chat/src/api/memory.ts`：7 端点客户端 + 类型
- `apps/web-chat/src/components/memory/`：
  - `MemoryList.vue`（列表 + 过滤）
  - `MemoryDetail.vue`（详情）
  - `MemoryEditForm.vue`（编辑表单）
  - `MemorySearchBar.vue`（搜索框 + top_k）
  - `MemoryAuditTimeline.vue`（审计历史）
- `apps/web-chat/src/views/MemoryDashboard.vue`（主页面）
- `apps/web-chat/src/router.ts`：加 1 路由 `/dashboard/memory`
- `apps/web-chat/src/types/api.ts`：追加 MemoryItem / MemoryAuditEvent / MemorySearchResult

**测试**：
- `apps/web-chat/src/api/memory.spec.ts`（8+ tests）
- 5 组件 specs（2-3 tests each）
- 1 view spec（2-3 tests）

**commit 规划**：3-4 commit
1. `feat(web-chat): memory API 客户端 + 类型`
2. `feat(web-chat): 5 memory widget + 1 view`
3. `feat(web-chat): router 加 /dashboard/memory 路由`
4. `style(web-chat): lint --fix（如需）`

---

## 四、4 个 WT 集成顺序

```
J1 (vector backend)  ─┐
J2 (enhancement)     ─┼─→ J3 (gateway API) → J4 (frontend) → 主控集成
J3 (gateway 独立)     ─┘
J4 (frontend 独立，依赖 J3 类型)
```

**主控集成顺序**：
1. cherry-pick / rebase J1 → J2 → J3 → J4 到 `integration/aigroup-wave6-1`
2. 集成期修复（接口冲突 / mypy 收尾 / ES 配置）
3. **关键：启 ES docker-compose**，跑端到端验证
4. 全量验证：pytest / mypy / ruff / 前端 type-check/test/lint/build
5. demo：5 条记忆写入 → 向量检索 → 按相关度召回 → 审计
6. 文档：`docs/memory-demos/README.md` + 收口记录
7. 合并 main + 推 GitHub + 清理 worktree

---

## 五、风险与边界

| 风险 | 缓解 |
|---|---|
| ES 服务启动慢、占内存 | 单测 mock ES 客户端（`MockElasticsearch`）；集成测试用 docker-compose；e2e 可选 |
| OpenAI Embedding API 真实调用扣 token | 单测用 FakeEmbedding；集成测试用 mock；真实 e2e 留 Wave 7（演示收口阶段） |
| 敏感信息过滤误伤（合法内容里含 "password" 关键词） | 过滤输出 warning 而非 fail；用户可手动 allowlist |
| 语义去重阈值 0.95 太严 / 太松 | 默认 0.95，可配置；写测试覆盖边界 |
| J1/J2 跨包接口（VectorMemoryBackend → SensitiveInfoFilter） | J1 不依赖 J2（filter 走 lifecycle 包装）；J2 注入 J1 backend |
| v1 §T3 MemoryItem 字段不破坏 | 复用现有字段；只加 source（可选） |
| 阶段 8 推迟 | 文档明确写"阶段 8 留 Wave 7"，不留半成品 |

---

## 六、收口判定

- [ ] 后端 pytest 全绿（基线 1232 + Wave 6.1 新增 ≥ 100）
- [ ] mypy 0 / ≥ 240 files（221 + 19-25 新文件）
- [ ] ruff 与 Wave 5.2 收口基线持平（45，**Wave 6.1 新增 0**）
- [ ] 前端 type-check / test / lint / build 全绿
- [ ] **ES docker-compose up 验证**：单测 + 集成测试通过
- [ ] **OpenAI Embedding 真实调用**（用 key 跑 1-2 个 case）— 用 Wave 4 真实 LLM case 模式
- [ ] 记忆增强 6 项全部实现（filter / dedup / conflict / audit / expire / fallback）
- [ ] 演示数据集 + 7 端点 dashboard 端到端跑通
- [ ] 收口记录 + 演示文档
- [ ] 4 个 Wave 6.1 worktree 合并后清理
- [ ] Ruff pre-existing 45 项基线（不阻塞 Wave 6.1 关闭）
- [ ] 阶段 8 演示收口留 Wave 7

---

## 七、Wave 6.1 → 后续

- **Wave 7**：阶段 8 端到端整合、演示与收口（Docker Compose 完整模式 + 5 演示用例 + 性能 / 安全基线 + README / 架构图）
- **Wave 8**：Cross-Encoder Reranker 升级（替换 BM25）+ 多租户隔离（如需）+ 部署

Wave 6.1 完成后，kivi-agent 记忆系统覆盖：本地 Markdown（Wave 1）+ 向量检索（Wave 6.1 J1）+ 语义去重 + 敏感信息过滤 + 审计（Wave 6.1 J2），为 Wave 7 完整演示提供基础。
