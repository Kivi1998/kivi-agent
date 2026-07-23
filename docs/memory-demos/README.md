# 长期记忆 + 向量检索演示

> Wave 6.1 收口演示：阶段 6 长期记忆 + ES 向量检索 + OpenAI Embedding，端到端跑通 8 个 Gateway 端点 + 前端 Memory 管理 UI。

## 核心组件

| 组件 | 文件 | 作用 |
|---|---|---|
| `MemoryBackend` Protocol | `src/kivi_agent/core/memory/backend.py` | 写/读/搜索/更新/删除/审计 6 方法 |
| `LocalMemoryBackend` | `src/kivi_agent/core/memory/local_backend.py` | 基于 Markdown 文件的本地实现（永远可用） |
| `VectorMemoryBackend` | `src/kivi_agent/core/memory/vector_backend.py` | ES 8.x + knn 向量检索（失败自动 fallback Local） |
| `EmbeddingProvider` Protocol | `src/kivi_agent/core/memory/embedding/protocol.py` | `async embed(texts) -> list[list[float]]` |
| `OpenAICompatEmbedding` | `src/kivi_agent/core/memory/embedding/openai_compat.py` | 调用 `${OPENAI_BASE_URL}/v1/embeddings`（也支持 `${ANTHROPIC_BASE_URL}`） |
| `FakeEmbedding` | `src/kivi_agent/core/memory/embedding/fake.py` | hash 映射 384 维，单测用，无 API 调用 |
| `BM25Reranker` | `src/kivi_agent/core/memory/rerank.py` | 简单 TF-IDF + cosine，Wave 7 升 Cross-Encoder |
| `MemoryLifecycle` | `src/kivi_agent/core/memory/lifecycle.py` | filter→dedup→write→audit 编排 |
| `MemoryItemStore` | `src/kivi_agent/core/memory/store.py` | 统一 Local/Vector 入口 + 单例可重置 |

## 6 项记忆增强

| 增强 | 文件 | 说明 |
|---|---|---|
| 敏感信息过滤 | `filter.py` | 正则：密码 / api_key / token / 邮箱 / 手机 / 身份证 |
| 语义去重 | `dedup.py` | cosine > 0.95 合并已有记忆 |
| 审计日志 | `audit.py` | JSONL 落盘 + 查询 API |
| 过期策略 | `expire.py` | 按 expires_at 自动 archive |
| 提取失败 fallback | `fallback.py` | safe_extract 永不 raise |
| 记忆类型 / 重要度 / 状态 | `types.py` | Literal 校验 |

## 8 个 Gateway 端点

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/memory/items` | 列表（按 status / memory_type / source 过滤） |
| GET | `/api/memory/items/{id}` | 单条 |
| POST | `/api/memory/items` | 手动创建 |
| PATCH | `/api/memory/items/{id}` | 更新字段 |
| DELETE | `/api/memory/items/{id}` | 删除 |
| POST | `/api/memory/items/{id}/archive` | 归档（软删） |
| GET | `/api/memory/search?q=...&top_k=5` | 向量检索 |
| GET | `/api/memory/audit?memory_id=...` | 审计历史 |

## 启动 ES（docker-compose）

```bash
# 启动 ES 8.13.4（1GB heap，security disabled for dev）
docker compose up -d elasticsearch

# 等 ES ready（约 30s）
curl -s http://localhost:9200/_cluster/health

# 跑 kivi-agent（会用 KIVI_ES_URL 自动发现）
KIVI_ES_URL=http://localhost:9200 \
KIVI_OPENAI_BASE_URL=https://api.openai.com \
KIVI_OPENAI_API_KEY=sk-... \
KIVI_MEMORY_BACKEND=vector \
KIVI_EMBEDDING_PROVIDER=openai \
uv run kivi-core
```

## 前端路由

| 路由 | 视图 |
|---|---|
| `/dashboard/memory` | MemoryDashboard（list + search + create + edit + archive + audit） |

## 验收标准对照（整合方案阶段 6）

| 验收 | 实现位置 |
|---|---|
| 小型本地模式不依赖外部数据库也能运行 | `LocalMemoryBackend` + 默认 `memory_backend=local` |
| 启用向量模式后只注入相关记忆 | `VectorMemoryBackend.search(query, top_k=5)` |
| 用户能查看/编辑/归档/删除记忆 | 8 端点 + 前端 MemoryDashboard |
| 记忆提取失败不影响主任务 | `MemoryExtractionFallback.safe_extract`（永不 raise） |

## 已知限制

- BM25Reranker 是 TF-IDF 简单版，Wave 7 升 Cross-Encoder
- 真实 OpenAI Embedding 调用需要 `OPENAI_API_KEY`（或 `ANTHROPIC_API_KEY`）；单测用 FakeEmbedding
- ES 8.13.4 需要 ~1GB 内存，本地启动较慢；集成测试通过 `KIVI_ES_URL` env guard
- 阶段 8（演示收口 / Docker Compose 完整模式 / 5 演示用例）留 Wave 7
