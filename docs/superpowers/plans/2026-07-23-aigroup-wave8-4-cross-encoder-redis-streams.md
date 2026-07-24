# aigroup Wave 8.4：Cross-Encoder Reranker + Redis Streams Exporter

> **基线**：`main @ ba781e8`（aigroup Wave 8.2 真实 LLM 端到端收口，1541 passed / 241 files）
> **日期**：2026-07-23
> **承接关系**：Wave 8.2 补齐真实 LLM 端到端。Wave 8.4 补齐 aigroup 未迁移的 2 个核心能力（Cross-Encoder 精排 + Redis Streams 事件分发）。
> **用户决定（2026-07-23）**：
>   1. 项目定位 = **个人项目 / 简历作品**——Wave 8.4 是 aigroup 未迁移能力的**最后一块技术拼图**，技术深度 + 简历亮点最高
>   2. **不引入 LangGraph / LangChain**——延续 Wave 0 决定
>   3. **默认不依赖 Redis / Cross-Encoder 模型**——env guard 守门，可选启用

---

## 一、目标

把"BM25Reranker 轻量级精排 + 进程内事件分发"升级为"Cross-Encoder 精排 + Redis Streams 事件分发"，补齐 aigroup 未迁移的两个核心能力：

```
现有（Wave 6.1 + Wave 7）
  BM25Reranker（轻量级关键词 + 向量相似度混合）
  事件直接走 WebSocket / TUI 轮询（不经过 Redis）
  EvalResultStore 进程内单例 + .jsonl 落盘
新增（Wave 8.4）
  Cross-Encoder Reranker（BERT-based 精排，RAG 准确率显著提升）
  Redis Streams Exporter（跨服务事件分发 + 持久化 + 多副本 Gateway）
  升级 BM25Reranker → CrossEncoderReranker（配置开关）
  升级进程内 EventBus → RedisStreamsExporter（可插拔）
```

**核心交付**：
- **Cross-Encoder Reranker**：`sentence-transformers` 集成（轻量级 ms-marco-MiniLM-L-6-v2，约 90MB） + `CrossEncoderReranker` 实现 + `Reranker` Protocol + 配置开关
- **Redis Streams Exporter**：`redis.asyncio` 集成（Redis 7+） + `RedisStreamsExporter` 实现 + `EventExporter` Protocol + 离线 fallback（Redis 不可用 → 进程内 JSONL）
- **多副本 Gateway 基础**：Redis Streams 作为事件总线，多个 Gateway 实例可水平扩展（demo 级别，1-2 实例）
- **完整文档 + 报告模板**：怎么启 Redis + 怎么选 reranker + 怎么验证多副本事件分发

**注意**：Wave 8.4 **默认仍用 BM25Reranker + 进程内事件总线**（向后兼容 Wave 6.1 + 7）。`KIVI_RERANKER=cross_encoder` + `KIVI_REDIS_STREAMS_ENABLED=1` 启用新能力。

---

## 二、范围

### 2.1 必做（Wave 8.4 范围）

| 序号 | 任务 | 估时 | 交付 |
|---|---|---|---|
| K1 | Cross-Encoder Reranker | 3-4 天 | `core/memory/rerank_cross_encoder.py` + Protocol + 配置 + tests |
| K2 | Redis Streams Exporter | 3-4 天 | `core/events/exporters/redis_streams.py` + Protocol + 配置 + tests |
| K3 | 多副本 Gateway demo | 2-3 天 | Gateway 接入 Redis Streams + 2 实例事件分发 E2E |
| K4 | 文档 + .env.example + RUNBOOK + 简历模板 | 1-2 天 | `docs/cross-encoder-redis/` + README + RUNBOOK 更新 |
| 主控 | 集成 + 全量验证 + 收口 | 1 天 | 集成 commit + 收口记录 |

**总估时**：10-14 天，4 WT 并行 + 集成

### 2.2 现有组件状态

Wave 6.1 已实现：
- `BM25Reranker`（`core/memory/rerank.py`）：轻量级关键词 + 向量相似度混合
- `LocalMemoryBackend` + `VectorMemoryBackend`（双后端，env guard 切换 ES）

Wave 5.1/5.2 + 7 已实现：
- `EvalResultStore` 进程内单例 + `.jsonl` 落盘
- 事件走 `EventBus` → `WebSocket` / `TUI` 轮询，**不经过 Redis**
- 单副本 Gateway（`uvicorn` 单进程）

需要补：
- **Cross-Encoder**：用 `sentence-transformers` 加载 ms-marco-MiniLM-L-6-v2，对召回 top_k=20 的候选精排到 top_n=5
- **Redis Streams**：`redis.asyncio` 集成，把 EventBus 事件写入 `kivi:events:stream`；消费者（Eval consumer / Dashboard / 监控）订阅 stream
- **多副本**：2 个 Gateway 实例共享同一个 Redis Stream，事件可被任一实例消费并广播给连接的 WebSocket 客户端

### 2.3 验收标准

| 验收 | 拆到哪个 WT 验证 |
|---|---|
| Cross-Encoder 精排 RAG 准确率提升 | K1（对照测试：BM25 vs Cross-Encoder 同数据集，RAG citation accuracy +10%）|
| Redis Streams 跨进程事件分发 | K2 + K3（2 实例 E2E：实例 A publish → 实例 B 收到） |
| 默认仍用 BM25Reranker + 进程内总线 | K1 + K2（向后兼容，env guard 守门） |
| Redis 不可用时降级到进程内 | K2（fallback 单元 + E2E） |
| Cross-Encoder 模型加载失败时降级到 BM25 | K1（fallback 单元 + E2E） |
| 完整文档 + 简历引用模板 | K4 |

---

## 三、4 个 WT 详细设计

### 3.1 K1：Cross-Encoder Reranker（核心交付 #1）

**目标**：用 BERT-based Cross-Encoder 精排 RAG 召回结果，准确率显著高于 BM25。

**关键文件**：
- `core/memory/rerank_protocol.py`：`Reranker` Protocol（已有 `BM25Reranker` 实现，需要提取 Protocol）
- `core/memory/rerank_cross_encoder.py`：`CrossEncoderReranker` 实现
- `core/memory/rerank_factory.py`：`get_reranker()` 根据 `KIVI_RERANKER` env var 选 BM25 / Cross-Encoder
- `core/memory/rerank_fallback.py`：模型加载失败时降级 BM25（永不 raise）
- `tests/unit/test_cross_encoder_reranker.py`：30+ 单元测试
- `tests/integration/test_cross_encoder_e2e.py`：5 case 真实模型 E2E（env guard `KIVI_RUN_CROSS_ENCODER=1`）

**核心设计**：
- 模型：`cross-encoder/ms-marco-MiniLM-L-6-v2`（Sentence-Transformers 官方，~90MB，CPU 可跑 ~50ms/对）
- 输入：query + 候选 passages（list[str]），输出：每个 passage 的 relevance score
- 精排流程：`vector search top_k=20` → `CrossEncoder rerank top_n=5` → 返回
- 降级策略：模型未安装 / 加载失败 / 推理超时 → 自动回退 BM25（log warning，不 raise）
- 配置：
  - `KIVI_RERANKER=bm25`（默认）| `cross_encoder`
  - `KIVI_CROSS_ENCODER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2`
  - `KIVI_CROSS_ENCODER_TIMEOUT_S=5.0`
  - `KIVI_CROSS_ENCODER_DEVICE=cpu`（默认）| `cuda`

**不允许**：
- 不引入 LangChain `CrossEncoderReranker`（重新实现）
- 不强制依赖 sentence-transformers（缺包时降级 BM25）
- 不修改 `LocalMemoryBackend` / `VectorMemoryBackend` 主体（只插拔 Reranker）

**对比测试**：
- 数据集：Wave 5.1 的 `docs/eval-demos/basic-routing-10cases.jsonl` + 5 条 RAG 检索 case
- 指标：`rag_citation_accuracy`（引用是否在 ground truth 中）
- 预期：Cross-Encoder 比 BM25 +5~10%（基于 MS MARCO 论文 baseline）

---

### 3.2 K2：Redis Streams Exporter（核心交付 #2）

**目标**：把 EventBus 事件通过 Redis Streams 导出，支持跨进程事件分发 + 持久化。

**关键文件**：
- `core/events/exporter_protocol.py`：`EventExporter` Protocol（`publish(event)` / `subscribe(pattern)` / `close()`）
- `core/events/exporters/redis_streams.py`：`RedisStreamsExporter` 实现（基于 `redis.asyncio`）
- `core/events/exporters/in_memory.py`：`InMemoryExporter`（当前默认行为，封装为 Exporter）
- `core/events/exporter_factory.py`：`get_exporter()` 根据 `KIVI_REDIS_STREAMS_ENABLED=1` 选 Redis 或 InMemory
- `core/events/redis_fallback.py`：Redis 不可用时降级 InMemory（永不 raise）
- `tests/unit/test_redis_streams_exporter.py`：30+ 单元测试（用 `fakeredis`）
- `tests/integration/test_redis_streams_e2e.py`：5 case 真实 Redis E2E（env guard `KIVI_RUN_REDIS=1`）

**核心设计**：
- Redis client：`redis.asyncio.Redis(host, port, db)`，默认 `localhost:6379/0`
- Stream key：`kivi:events:stream`（XADD 追加 + XREAD 消费）
- 事件格式：`event_type | run_id | timestamp | payload_json`
- 消费模式：每个 Gateway 实例用 `XREAD BLOCK 5000 STREAMS kivi:events:stream $` 拉新事件，再广播给本地 WebSocket 客户端
- 持久化：Redis AOF 默认开启（事件不丢）
- 降级策略：Redis 不可用 / 连接超时 → 自动回退 InMemoryExporter（log warning，不 raise）
- 配置：
  - `KIVI_REDIS_STREAMS_ENABLED=0`（默认）| `1`
  - `KIVI_REDIS_URL=redis://localhost:6379/0`
  - `KIVI_REDIS_STREAM_KEY=kivi:events:stream`
  - `KIVI_REDIS_CONSUMER_GROUP=kivi-gateway-{instance_id}`
  - `KIVI_REDIS_TIMEOUT_S=2.0`

**不允许**：
- 不引入 Celery / Kafka（直接用 Redis Streams 原生）
- 不修改 `EventBus` 内部实现（只在 publish 时多调一次 Exporter）
- 不破坏现有 WebSocket 客户端（Exporter 是增量能力）

**Redis Stream 数据结构**：
```
XADD kivi:events:stream * event_type "LlmTokenEvent" run_id "run-xxx" ts "2026-07-23T22:00:00Z" payload '{"token":"Hello","step":1}'
```

---

### 3.3 K3：多副本 Gateway 接入 Redis Streams

**目标**：演示 2 个 Gateway 实例共享 Redis Stream，事件可被任一实例消费并广播给本地 WebSocket 客户端。

**关键文件**：
- `gateway/main.py`：实例启动时注册 Exporter 消费者（`asyncio.create_task(_consume_redis_stream())`）
- `gateway/consumer.py`：Redis Stream → 本地 WebSocket 广播
- `docker-compose.yml`：加 Redis service + 第 2 个 Gateway 实例（端口不同）
- `tests/integration/test_multi_gateway_e2e.py`：2 实例事件分发 E2E（env guard `KIVI_RUN_REDIS=1` + `KIVI_RUN_MULTI_GATEWAY=1`）
- `docs/architecture/multi-gateway.md`：架构图 + 部署说明

**核心设计**：
- Gateway A（端口 8080）+ Gateway B（端口 8081）共享 `redis://redis:6379/0`
- Run 在 Gateway A 创建 → 事件 `XADD kivi:events:stream * ...`
- Gateway B 的 consumer 拉到事件 → 广播给 Gateway B 的所有 WebSocket 客户端
- Consumer group：`kivi-gateway-{instance_id}`（每个实例独立 group，事件被所有实例消费）
- 健康检查：`/health/detailed` 加 `redis_connected` 字段（true / false / fallback）

**测试场景**：
1. 启动 Redis + 2 个 Gateway 实例
2. WebSocket 客户端连 Gateway A
3. WebSocket 客户端连 Gateway B
4. 创建 Run（走 Gateway A 的 FastAPI）→ 事件 XADD
5. 断言：两个 WebSocket 客户端都收到完整事件流（包括 LlmTokenEvent / LlmUsageEvent / ToolCallEvent）
6. 停止 Gateway A → 断言 Gateway B 仍可正常工作

**不允许**：
- 不做负载均衡（demo 级别，手动指定 Gateway）
- 不做 session 共享（Run ID 由 Gateway A 创建，事件通过 Redis 广播到 B）
- 不做 sticky session（WebSocket 客户端可连任一实例）

---

### 3.4 K4：文档 + .env.example + RUNBOOK + 简历模板

**目标**：完整用户指南，简历可引用。

**关键文件**：
- `docs/cross-encoder-redis/README.md`：Cross-Encoder + Redis Streams 启用指南（~600 行）
- `docs/cross-encoder-redis/RESULTS_TEMPLATE.md`：基准测试报告模板（~400 行，含 §4 简历引用模板）
- `docs/architecture/multi-gateway.md`：多副本架构图 + 部署说明（K3 协作，~300 行）
- `.env.example`：加 8 段（`KIVI_RERANKER` / `KIVI_CROSS_ENCODER_*` / `KIVI_REDIS_STREAMS_ENABLED` / `KIVI_REDIS_*`）
- `docker-compose.yml`：加 Redis service（K3 协作）
- `RUNBOOK.md`：+§5 Cross-Encoder & Redis Streams（~250 行）
- `README.md`：+§Quick Start: Cross-Encoder & Redis（~60 行）
- `MIGRATION.md`：+§1.10 Wave 8.4 + §3.4 更新（标记完成）

**核心内容**：
- §1 启用 Cross-Encoder：`pip install sentence-transformers` + `export KIVI_RERANKER=cross_encoder`
- §2 启用 Redis Streams：`docker run -d -p 6379:6379 redis:7-alpine` + `export KIVI_REDIS_STREAMS_ENABLED=1`
- §3 多副本 Gateway 部署：`docker-compose up -d`（自动起 2 个 Gateway + Redis）
- §4 基准测试：BM25 vs Cross-Encoder 同数据集对比 + 单副本 vs 多副本延迟对比
- §5 简历引用模板：直接抄

---

## 四、契约冻结（pre-merge）

| 契约 | 版本 | 位置 | 必填字段 |
|---|---|---|---|
| `Reranker` Protocol | v1 | `core/memory/rerank_protocol.py` | `name: str` / `rerank(query, candidates, top_n) -> list[ScoredDoc]` |
| `EventExporter` Protocol | v1 | `core/events/exporter_protocol.py` | `publish(event)` / `subscribe(pattern)` / `close()` |
| Redis Stream 消息格式 | v1 | `core/events/exporters/redis_streams.py` | `event_type` / `run_id` / `ts` / `payload` |
| `RerankResult` 数据类 | v1 | `core/memory/types.py` | `id` / `text` / `score` / `metadata` |
| `ExporterConfig` 数据类 | v1 | `core/events/exporters/config.py` | `enabled` / `url` / `stream_key` / `consumer_group` / `timeout_s` |

**v1 契约冻结后，4 个 WT 只能实现接口**。如需改契约，必须先停止相关 WT，由主控升级版本。

---

## 五、4 个 WT 派工

| WT | 独占范围 | 关键文件 | 不应修改 |
|---|---|---|---|
| **K1 Cross-Encoder** | `core/memory/rerank_*.py` + tests | `rerank_protocol.py` / `rerank_cross_encoder.py` / `rerank_factory.py` / `rerank_fallback.py` + `tests/unit/test_cross_encoder_reranker.py` + `tests/integration/test_cross_encoder_e2e.py` | `core/memory/local_backend.py` / `core/memory/vector_backend.py`（只通过 Protocol 调用）|
| **K2 Redis Streams Exporter** | `core/events/exporters/` + tests | `exporter_protocol.py` / `exporters/redis_streams.py` / `exporters/in_memory.py` / `exporter_factory.py` / `redis_fallback.py` + `tests/unit/test_redis_streams_exporter.py` + `tests/integration/test_redis_streams_e2e.py` | `core/events/bus.py`（只在 publish 处加 hook）|
| **K3 多副本 Gateway** | `gateway/main.py` + `gateway/consumer.py` + `docker-compose.yml` + 多副本 E2E | `gateway/main.py` / `gateway/consumer.py` / `docker-compose.yml` + `tests/integration/test_multi_gateway_e2e.py` + `docs/architecture/multi-gateway.md` | 业务 Tool / Eval / Memory（只通过 EventExporter 接入）|
| **K4 文档** | `docs/cross-encoder-redis/` + `.env.example` + `RUNBOOK.md` + `README.md` + `MIGRATION.md` | 文档 + 模板 | 源码（只在最后阶段更新）|

**4 WT 并行**（K1 / K2 / K3 / K4 互不冲突的目录）→ 主控集成 → 全量验证 → 收口 commit + push + cleanup。

---

## 六、不应做（明确边界）

- ❌ 不引入 LangChain `CrossEncoderReranker`（自己实现）
- ❌ 不引入 Celery / Kafka（用 Redis Streams 原生）
- ❌ 不做 session 共享（demo 级别，2 实例即可）
- ❌ 不做 sticky session / 负载均衡（按需扩展）
- ❌ 不强制依赖 sentence-transformers / redis（env guard 守门 + fallback）
- ❌ 不修改 Wave 1-8.2 已冻结的契约（v1 不变）
- ❌ 不修改 LangGraph / LangChain 决定（不引入）

---

## 七、风险与控制

| 风险 | 表现 | 控制措施 |
|---|---|---|
| Cross-Encoder 模型下载失败 | 首次启动卡 5+ 分钟 | 离线模型 + `KIVI_CROSS_ENCODER_MODEL` env 允许指定本地路径 |
| Redis 不可用 | Gateway 起不来 / 事件丢 | fallback InMemoryExporter + log warning + 不 raise |
| Cross-Encoder 推理慢 | RAG 检索延迟 +500ms | CPU 推理 + `KIVI_CROSS_ENCODER_TIMEOUT_S=5.0` + 自动降级 BM25 |
| 多副本事件乱序 | 同一 run_id 事件被不同 consumer 拉走导致乱序 | consumer group + 单 run_id 路由到同一实例（demo 级别不做，文档说明）|
| Redis Stream 内存增长 | 事件堆积占内存 | `MAXLEN ~ 100000` 自动截断 + 监控脚本 |

---

## 八、估时

- K1 Cross-Encoder：3-4 天（含对比测试 + 降级 + 文档）
- K2 Redis Streams Exporter：3-4 天（含 fallback + 单元 + 集成）
- K3 多副本 Gateway：2-3 天（Redis 服务 + 2 实例 E2E + 架构图）
- K4 文档：1-2 天（README + RESULTS_TEMPLATE + RUNBOOK + 简历模板）
- 主控集成：1 天（cherry-pick + reconcile + 全量验证 + 收口）
- **总计**：10-14 天

**短期里程碑**：
- Day 1-2：4 WT 启动（plan + 契约冻结 + worktree 创建）
- Day 3-7：4 WT 并行实现
- Day 8-10：主控 cherry-pick + 集成 reconcile
- Day 10-12：全量验证（pytest / mypy / ruff / 前端）
- Day 12-14：收口 + push + 清理

---

## 九、最终交付

- ✅ Cross-Encoder Reranker 完整实现（生产可用 + fallback）
- ✅ Redis Streams Exporter 完整实现（生产可用 + fallback）
- ✅ 多副本 Gateway demo（2 实例 + Redis 共享事件流）
- ✅ 完整文档（启用指南 + 架构图 + 报告模板 + 简历引用）
- ✅ 测试覆盖：unit + integration + E2E（K1 + K2 + K3 共 ~100 新 test）
- ✅ 全量验证：pytest 1640+ passed / mypy 0 / ruff 45 / 前端 181+ tests

**aigroup Wave 8.4 收官完成：Cross-Encoder 精排 + Redis Streams 事件分发补齐 aigroup 未迁移 2 个核心能力，与 Wave 8.2 真实 LLM 端到端形成完整「RAG 精排 + 事件分发 + 真 LLM」简历作品三件套。**
