# aigroup Wave 7 集成报告（占位文件）

> **基线**：`main @ b211fc7`（Wave 6.1 收官后） → `integration/aigroup-wave7`（本文件待主控集成期填写）
> **日期**：2026-07-23
> **占位**：本文件由主控 agent 在 Wave 7 集成期填写，作为收口记录。
> **本文件当前状态**：**占位**，仅含模板 + 子包 commit 列表占位 + 集成顺序占位。
> **填写真实数据**应参考 [docs/迁移记录/最小闭环验收记录.md](../迁移记录/最小闭环验收记录.md) 历史 Wave 写法。

---

## 待填：1. 子包 commit 列表

> 主控集成后填写。

| WT | 范围 | 净 commit | 关键 commit |
|---|---|---|---|
| K1 | Docker Compose 三模式 + 启动脚本 + 凭据清理 | TBD | TBD |
| K2 | 5 演示用例脚本化（含 MapLoadTool + MapView.vue） | TBD | TBD |
| K3 | 故障注入 + 性能基线 + 安全基线 | TBD | TBD |
| K4 | README + 架构图 + 开发指南 + 演示手册 + 迁移清单 | **已合并** | 见下表 |
| 主控 | 集成 + 全量验证 + 收口 | TBD | TBD |

**K4 commit 列表**（本 worktree `integration/aigroup-wave7-docs`）：

| # | hash | subject |
|---|---|---|
| 1 | 8e27a00 | docs: README.md 重写（按 stage 8 验收：可启动 / 5 demo / 不退化） |
| 2 | a7cdb15 | docs: RUNBOOK.md + docs/architecture/architecture.md + data-flow.md |
| 3 | 3d3b77f | docs: docs/development/contributing.md + modules.md |
| 4 | f818470 | docs: docs/demo/ 5 演示手册 |
| 5 | TBD | docs: MIGRATION.md（已迁移/未迁移/后续计划） |

## 待填：2. 集成合并顺序

> 主控集成后填写。

```text
1. git checkout integration/aigroup-wave7
2. git merge --no-ff k4/docs -m "merge: K4 README + 架构图 + 开发指南 + 演示手册 + 迁移清单"
3. (K1, K2, K3 合并顺序待主控决定)
4. 全量验证：pytest / mypy / ruff / 前端 type-check/test/lint/build / 5 demo
5. 集成 commit：fix integration issues
6. 收口 commit：docs: Wave 7 集成报告 + 验收判定
7. 推 + 提 PR + merge to main
```

## 待填：3. 集成验证数据

> 主控集成后填写（参考 Wave 6.1 收口报告格式）。

### 后端

- `uv run pytest -q` → TBD passed / TBD skipped / 0 failed / 7 errors (pre-existing)
- `uv run mypy src` → TBD errors / TBD source files
- `uv run ruff check src tests` → 45 errors（baseline 一致，Wave 7 新增 0）

### 前端

- `npm run type-check` → TBD error
- `npm test` → TBD passed / TBD files
- `npm run lint` → TBD error / TBD warning
- `npm run build` → success（TBD kB）

### 5 演示

- `uv run python -m demos.run_all` → TBD / 5 passed
- 报告输出：`reports/demo_summary.json`

### Docker Compose 三模式

- minimal：`./scripts/start.sh --mode minimal` → `curl /health` 200
- web：`./scripts/start.sh --mode web` → `curl /api/dashboard/summary` 200
- full：`./scripts/start.sh --mode full` → `curl /_cluster/health` green

### 故障注入

- `tests/integration/test_failure_injection.py` → 5/5 passed

### 性能基线

- `tests/performance/test_benchmarks.py` → 3/3 passed
- 报告输出：`reports/benchmark_*.json`

### 安全基线

- `tests/security/test_security_baseline.py` → 4/4 passed

## 待填：4. 集成期发现与调整

> 主控集成后填写（按 Wave 6.1 收口报告格式）。

| 项 | 调整 | 性质 | 修复 commit |
|---|---|---|---|
| TBD | TBD | TBD | TBD |

## 待填：5. 验收判定

- [ ] 后端 pytest 全绿（TBD passed / ≥ 1407）
- [ ] mypy 0 / TBD files（≥ 235）
- [ ] ruff 45 errors（baseline 一致，Wave 7 新增 0）
- [ ] 前端 type-check / test / lint / build 全绿（≥ 178 tests）
- [ ] Docker Compose 三模式可启（minimal / web / full，curl 验证）
- [ ] 5 演示用例全过（demo1-5 端到端跑通，报告输出）
- [ ] 故障注入 5 场景全过（model / tool timeout / subagent / ws / cancel）
- [ ] 性能基线 3 模式报告输出（reports/benchmark_*.json）
- [ ] 安全基线 4 场景全过（path / bash / skill / frontend spoofing）
- [ ] 历史 .env 真 KEY 已清（git filter-repo 验证）
- [ ] README + RUNBOOK + 架构图 + 5 demo 手册 + MIGRATION 完整
- [ ] 4 个 Wave 7 worktree 合并后清理
- [ ] Ruff pre-existing 45 项基线（不阻塞 Wave 7 关闭）

**Wave 7 收口完成**（待勾选）。

## 待填：6. 与整合方案对齐

| 方案 | 实际 | 偏差 |
|---|---|---|
| 阶段 8 12 项任务 | TBD / 12 完成 | 0 |
| 阶段 8 4 项验收 | 4 / 4 通过 | 0 |

## 7. 后续 Wave 8 候选

按 [MIGRATION.md §3](../../MIGRATION.md)：

- Wave 8.1：生产部署（k8s / Helm / TLS / 多副本）
- Wave 8.2：真实 LLM 端到端
- Wave 8.3：多租户隔离
- Wave 8.4：Cross-Encoder + Redis Streams

是否进入 Wave 8 取决于"对内演示 / 对外开源 / 公司生产"的最终方向（用户尚未答复）。

---

## 模板参考

填本文件时请参考 [docs/迁移记录/最小闭环验收记录.md](../迁移记录/最小闭环验收记录.md) 历史 Wave 收口报告格式：
- 一句话总结
- 子包总览（commit 数 + 关键文件）
- 集成合并顺序
- 集成验证（后端 + 前端 + 端到端）
- 关键调整
- 关闭判定
- 最终全局状态
