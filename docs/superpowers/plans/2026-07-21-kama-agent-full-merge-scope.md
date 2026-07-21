# kamaAgent 个人版全功能合并 — 总览与分包计划

> **For agentic workers:** 这是一份索引/总览文档，不是可直接逐步执行的 TDD 任务清单。已经具备完整 TDD 步骤、可直接执行的是 [`2026-07-20-kama-agent-minimal-loop.md`](2026-07-20-kama-agent-minimal-loop.md)（下称"基础闭环计划"）。本文档把 mewcode 全部 44 项能力（M01～M44，不含企业治理 E01～E25）逐一映射到 KamaClaude 的具体目标模块，分成 8 个子计划包。每个子计划包在被执行前，应先用 superpowers:writing-plans 展开成和基础闭环计划同等粒度（每步完整代码、失败测试→实现→通过测试→提交）的独立文件。

**为什么要分包而不是一份 130 步的巨型计划**：这是 superpowers:writing-plans 的 Scope Check 要求——覆盖多个独立子系统的 spec 应该拆成多份子计划，每份都能独立产出可运行、可测试的软件。这里的 8 个包彼此依赖较弱（Teams 依赖 Subagent 已有能力但不依赖 Skills/MCP 增强），可以按需单独展开、单独执行、单独验收。

**范围边界**：只合并 mewcode 的能力（M01～M44）。企业治理层（SSO/RBAC/模型网关/高可用/网页工作台等，E01～E25）不在个人版范围内——这类能力天然需要多人协作和基础设施，硬塞进"个人版"没有意义，见此前对话已确认。

---

## 全景表：M01～M44 全部映射到位

| 编号 | mewcode 能力 | KamaClaude 现状 | 目标改动 | 所属子计划包 |
|---|---|---|---|---|
| M01 | 多模型 ProviderConfig | 只有 Anthropic | Task 6-7（基础闭环）已做 OpenAI 兼容一种协议 | 基础闭环（已完成设计） |
| M02 | Anthropic 流式适配 | 已有 `AnthropicProvider`，含重试 | 保留，无需改动 | — |
| M03 | OpenAI 协议适配 | 同 M01，OpenAI 兼容≈OpenAI 协议 | 基础闭环已覆盖，此项不再单独做 | 基础闭环（已完成设计） |
| M04 | OpenAI 兼容协议 | 同上 | 基础闭环 Task 6 已做 | 基础闭环（已完成设计） |
| M05 | 模型上下文窗口解析 | `provider.py::_context_window` 是写死的字典 | 改成可配置+运行时探测+默认回退 | 包 B |
| M06 | 流式响应收集器 | `AnthropicProvider.chat()`/`OpenAICompatProvider.chat()` 各自处理流式，无统一收集器抽象 | 抽出 `StreamCollector` 统一两个 Provider 的增量聚合逻辑 | 包 B |
| M07 | 并发工具批次 | `invoke_tool()` 逐个顺序调用，无批次概念 | 新增 `partition_tool_calls`+并发执行只读工具 | 包 B |
| M08 | 工具动态搜索 | 无；`ToolRegistry` 一次性把所有工具 schema 都推给 LLM | 新增 `tool_search` 工具+`should_defer`标记机制 | 包 B |
| M09-M12 | Glob/Grep/EditFile/Diff | 无 | 基础闭环 Task 2-5 已做 | 基础闭环（已完成设计） |
| M13 | AskUser 交互工具 | 无用户中途提问机制 | 新增 `ask_user` 工具+`asyncio.Future`挂起+TUI 弹窗 | 包 C |
| M14 | 计划模式 | 无 | 新增 `PermissionMode.PLAN`+`exit_plan_mode`工具+TUI 计划对话框 | 包 D（并入权限模式） |
| M15 | 文件状态缓存 | 无 staleness 检测 | 新增 `FileStateCache`，`read_file`记录、`edit_file`校验 | 包 C |
| M16 | 文件历史 | 无（EditFileTool 只做原子写，不留版本） | 新增 `FileHistory`：每次编辑前存快照、支持 `rewind` | 包 C |
| M17-M18 | Git 工作树 | 无 | 基础闭环 Task 8-9 已做 | 基础闭环（已完成设计） |
| M19 | 权限模式 | 只有 `PermissionDecision(ALLOW/DENY/ASK)` 三态，无模式切换 | 新增 `PermissionMode(DEFAULT/ACCEPT_EDITS/PLAN/BYPASS)`+矩阵决策 | 包 D |
| M20 | 权限交互对话框 | TUI 已有 `PermissionSelect`/`PermissionBlock`（够用） | 只需适配新增的 PLAN 模式展示，不算新组件 | 包 D |
| M21 | 生命周期钩子 | 无 hooks 模块，只能订阅 EventBus 做"伪后置钩子" | 新增 `core/hooks/`：事件枚举+前置可拒绝+后置异步 | 包 D |
| M22 | 工具拒绝与钩子错误 | `invocation.py` 已有 `_RETRYABLE`重试分类 | 扩展错误分类支持 `ToolRejectedError`（钩子拒绝） | 包 D |
| M23-M24 | 沙箱+网络控制 | 无 | 基础闭环 Task 10-11 已做（缺网络白名单细粒度控制） | 基础闭环（已完成设计，网络白名单增强见包 D） |
| M25 | 上下文自动压缩 | 已有 `Compactor.compact()`，无熔断 | 保留，与 M28 一起加固 | 包 E |
| M26 | 替换记录状态 | `SessionStore` 只有整体备份（`thread_<ts>.jsonl.bak`），无逐条替换记录 | 新增细粒度 `ReplacementRecord`：记录哪条消息被摘要替换，支持重建 | 包 E |
| M27 | 恢复状态 | 无失败点检查/重入机制（S6/S7 阶段未做） | 新增运行检查点：关键步骤后持久化，重启可续跑 | 包 E |
| M28 | 压缩熔断 | 无——`compact()`失败只是静默跳过，下一步继续无脑重试 | 新增失败计数+阈值降级（连续 N 次失败后跳过压缩、告警） | 包 E |
| M29 | 工具输出预算 | 已有 `CompactionConfig.tool_result_limit/keep`（字符截断），概念已存在但未做"落盘+占位符"式预算 | 加固为 mewcode 风格：超限落盘、对话里留 `[persisted]` 占位符 | 包 E |
| M30 | 自动记忆 | 无长期记忆模块，只有 session 内 `notes.md` | 新增 `core/memory/`：`.md`文件+索引+自动抽取+召回注入 | 包 E |
| M31 | 会话选择与恢复界面 | TUI 无 Session 列表/切换界面，只有 CLI `--replay` | 新增 TUI Screen：列出/切换/恢复历史会话 | 包 H |
| M32-M36 | 团队/协调者/消息/工作树隔离 | 已有单层 Subagent（`spawn_agent`+`BackgroundTaskRegistry`，深度上限2），无"团队"概念 | 在现有 Subagent 基础上加 Team/Coordinator/Mailbox | 包 F |
| M37 | 技能安装 | `SkillLoader`只会从本地 `.kama/skills/`/`~/.kama/skills/`加载，无安装能力 | 新增 `skills/install.py`：从 GitHub 拉取+校验+原子落地 | 包 G |
| M38 | 技能搜索与加载 | `SkillLoader.resolve/list_all_skills`已有基本查找 | 加"关键词搜索"（复用包 B 的 tool_search 打分思路） | 包 G |
| M39 | MCP HTTP/SSE | 已支持 stdio + TCP，无 HTTP/SSE | 新增 `connect_http`（streamable_http）传输 | 包 G |
| M40 | MCP 密钥引用 | `McpServerConfig`里 `env: dict[str,str]`是明文 | 改为支持 `${SECRET:NAME}`引用，运行时从环境变量解析，不落盘明文 | 包 G |
| M41 | 终端计划对话框 | 无（配合 M14） | 新增 `PlanDialog` Textual 组件 | 包 H |
| M42 | 终端权限对话框 | 已有基础版（`PermissionSelect`），需支持断线重连后状态不丢失 | 审批状态从"内存态"改为可从 `PermissionManager._pending`恢复 | 包 D（顺带做，不单开） |
| M43 | 终端团队树 | 无（配合 M32-36） | 新增 `TeamTreeWidget`：展示团队成员树状态 | 包 H |
| M44 | 远程连接思路 | 无 Gateway（个人版明确不做，见范围边界） | 只借鉴"断线重连+事件位置续传"的思路，用于 M31 会话恢复界面，不新建组件 | 并入包 H（M31 里体现） |

---

## 8 个子计划包

### 已完成设计并可直接执行

**基础闭环计划**（[`2026-07-20-kama-agent-minimal-loop.md`](2026-07-20-kama-agent-minimal-loop.md)，11 个任务）
覆盖 M01/M03/M04（部分）、M09-M12、M17-M18、M23-M24（部分）。这是唯一已经写到"每步完整代码"粒度、可以直接丢给 coding agent 执行的文件。

### 已展开为完整 TDD 计划

- **包 D**（[`2026-07-21-kama-agent-package-d-permissions-hooks.md`](2026-07-21-kama-agent-package-d-permissions-hooks.md)，8 个任务）——权限模式 + 钩子
- **包 E**（[`2026-07-21-kama-agent-package-e-context-memory.md`](2026-07-21-kama-agent-package-e-context-memory.md)，7 个任务）——上下文韧性 + 长期记忆

两份都已经是和基础闭环计划同等粒度（完整代码+测试+commit），可以直接执行。**包 D 的 Task D1 新增了 `BaseTool.category` 字段，这是和包 B 之间新发现的耦合点**——两包并行执行时务必对齐字段名和取值（`"read"|"write"|"command"|"other"`），细节见包 D 文档的 Global Constraints。

### 待展开为完整 TDD 计划的剩余 5 个包

**包 B：模型能力与工具执行增强**（对应 M05-M08）
- 目标文件：`core/llm/catalog.py`（新建，上下文窗口配置+探测）、`core/llm/streaming.py`（新建，`StreamCollector`抽象，`AnthropicProvider`/`OpenAICompatProvider`改为复用它）、`core/tools/executor.py`（新建，`partition_tool_calls`+并发批次）、`core/tools/builtin/tool_search.py`（新建）、`core/tools/registry.py`（改，加`should_defer`/`mark_discovered`/`search`）
- 关键设计点：并发安全性判断复用 mewcode 的"`category=="read"`才能并发"规则；KamaClaude 现有工具里 `read_file`/`list_dir`/`glob`/`grep`/`diff` 应标为 `category="read"`，`bash`/`write_file`/`edit_file` 保持串行
- 依赖：无前置依赖，可独立展开

**包 C：交互工具与文件安全**（对应 M13/M15/M16）
- 目标文件：`core/tools/builtin/ask_user.py`（新建）、`tui/ask_user_dialog.py`（新建 Textual 组件）、`core/tools/file_state_cache.py`（新建）、`core/tools/builtin/edit_file.py`（改，接入 staleness 检查）、`core/filehistory/history.py`（新建）
- 关键设计点：`ask_user` 的挂起机制直接复用基础闭环计划里 `PermissionManager.check_and_wait` 已验证过的 `asyncio.Future` 模式，不用重新发明
- 依赖：`edit_file.py` 依赖基础闭环计划 Task 4 已存在

**包 D：权限模式与钩子**（对应 M14/M19-M22，含 M24 网络白名单增强、M42 断线重连）
- 目标文件：`core/permissions/modes.py`（新建，`PermissionMode`枚举+决策矩阵）、`core/permissions/manager.py`（改，接入 mode）、`core/hooks/`（新建包：`events.py`/`models.py`/`engine.py`/`loader.py`）、`core/tools/invocation.py`（改，插入 pre/post hook 调用点）、`core/tools/builtin/exit_plan_mode.py`（新建）
- 关键设计点：Hooks 的插入点已经在研究中定位——`core/tools/invocation.py::invoke_tool()` 里 `ToolCallStartedEvent` 发布前后就是 pre/post hook 的位置，不需要改动 `core/loop.py`
- 依赖：无前置依赖，是包 F（Teams）未来做"团队策略钩子"的基础设施，建议优先展开

**包 E：上下文韧性与长期记忆**（对应 M25-M31 除 M31 界面部分）
- 目标文件：`core/compact/compactor.py`（改，加失败计数熔断）、`core/session/replacement.py`（新建，细粒度替换记录）、`core/runner.py`（改，运行检查点持久化）、`core/context/manager.py`（新建或改，工具输出预算落盘+占位符）、`core/memory/`（新建：`store.py`/`extractor.py`/`recall.py`，`.md`文件+`MEMORY.md`索引，参考 mewcode 的 frontmatter 格式）
- 关键设计点：长期记忆刻意不做"consolidation/dream"（mewcode M30 里那个需要文件锁+24h门槛的后台合并子 Agent）——个人单机场景没有多进程并发写记忆的问题，这部分可以简化，只做抽取+召回，不做定时合并
- 依赖：无前置依赖，是最值得优先展开的包之一（直接提升长任务稳定性，是原企业方案里的 P0 项）

**包 F：多 Agent 团队协作**（对应 M32-M36）
- 目标文件：`core/teams/models.py`（新建，`AgentTeam`/`TeammateInfo`）、`core/teams/mailbox.py`（新建，文件系统邮箱，直接复用 mewcode 的 `O_CREAT|O_EXCL` 自旋锁设计——这部分是通用的跨进程互斥技巧，不依赖 mewcode 私有类型，可以直接迁移思路）、`core/teams/manager.py`（新建）、`core/tools/builtin/team_create.py`/`team_message.py`（新建）
- 关键设计点：只做 `spawn_inprocess` 一种后端（`asyncio.create_task`同进程协程），不做 mewcode 的 `spawn_tmux`（需要用户本机装 tmux，个人闭环没必要），团队本质是"KamaClaude 已有的 Subagent 机制 + mailbox 通信 + 深度限制放宽"
- 依赖：建议在包 D（Hooks）之后展开，团队协调策略后续可以用钩子约束"协调者只能调度不能编码"

**包 G：技能分发与 MCP 扩展**（对应 M37-M40）
- 目标文件：`core/skills/install.py`（新建，GitHub Contents API 拉取+落地）、`core/skills/loader.py`（改，加关键词搜索）、`core/mcp/client.py`（改，加 `connect_http`）、`core/config.py`（改，`McpServerConfig.env`支持 `${SECRET:NAME}`语法）
- 关键设计点：不做签名校验（mewcode 本身也没做，只有体积/路径限制），个人场景下技能来源可信度由用户自己把关
- 依赖：无前置依赖，可独立展开，优先级最低（对最小闭环的核心体验提升有限）

**包 H：TUI 增强**（对应 M31/M41/M43/M44）
- 目标文件：`tui/session_screen.py`（新建，会话列表/切换/恢复）、`tui/plan_dialog.py`（新建）、`tui/team_tree.py`（新建）
- 关键设计点：当前 `tui/app.py` 是单文件承载所有 Widget，这个包展开时第一步应该是先把已有 Widget 拆分成独立文件（`PermissionSelect`/`PermissionBlock`挪到 `tui/permission_widgets.py`），再加新组件，避免单文件继续膨胀
- 依赖：`session_screen.py` 依赖包 E 的运行检查点（要展示"可恢复"状态得先有检查点数据），`team_tree.py` 依赖包 F

---

## 建议展开顺序

1. **包 D（权限模式+钩子）**——基础设施，后续包依赖它的扩展点
2. **包 E（上下文韧性+长期记忆）**——原企业方案里唯一被标 P0 的个人可做项，直接解决"长任务不稳定"这个真实痛点
3. **包 B（模型/工具执行增强）**——独立，随时可做
4. **包 C（交互工具+文件安全）**——独立，随时可做
5. **包 F（团队协作）**——依赖包 D
6. **包 G（技能+MCP）**——独立，优先级最低
7. **包 H（TUI）**——依赖包 E、包 F，放最后

---

## 四路并行分工（4 个 subagent 同时干活）

7 个包之间的真实依赖只有两条：**F 依赖 D**、**H 依赖 E 和 F**。其余（B/C/D/E/G）互相独立。据此排出 3 波，每波最多 4 个 agent 同时跑，全程不出现"某个 agent 等另一个 agent 才能开工"的空转：

### 第 1 波（4 个 agent 并行，互不依赖）

| Agent | 负责包 | 交付物 |
|---|---|---|
| Agent 1 | **包 D** 权限模式+钩子 | `core/permissions/modes.py`、`core/permissions/manager.py` 改动、`core/hooks/`、`core/tools/invocation.py` 改动、`core/tools/builtin/exit_plan_mode.py` |
| Agent 2 | **包 E** 上下文韧性+长期记忆 | `core/compact/compactor.py` 改动、`core/session/replacement.py`、`core/runner.py` 检查点改动、`core/context/manager.py`、`core/memory/` |
| Agent 3 | **包 B** 模型能力+工具执行增强 | `core/llm/catalog.py`、`core/llm/streaming.py`、`core/tools/executor.py`、`core/tools/builtin/tool_search.py`、`core/tools/registry.py` 改动 |
| Agent 4 | **包 C** 交互工具+文件安全 | `core/tools/builtin/ask_user.py`、`tui/ask_user_dialog.py`、`core/tools/file_state_cache.py`、`core/tools/builtin/edit_file.py` 改动、`core/filehistory/history.py` |

### 第 2 波（2 个 agent 并行，D 已交付，F 解锁）

| Agent | 负责包 | 前置条件 |
|---|---|---|
| Agent 1 | **包 F** 多 Agent 团队协作 | 需要第 1 波 Agent 1（包 D）已合并，因为团队协调策略要用钩子约束"协调者只调度不编码" |
| Agent 2 | **包 G** 技能分发+MCP 扩展 | 无前置条件，第 1 波就能塞进去，放第 2 波纯粹是优先级最低、不抢第 1 波资源 |

第 2 波空出来的另外 2 个 agent 名额，建议不要闲置——用来做**第 1 波四个包的集成回归**（见下面"集成风险"），而不是提前开工包 H（H 的前置条件在这一波结束前还不满足）。

### 第 3 波（1 个 agent）

| Agent | 负责包 | 前置条件 |
|---|---|---|
| Agent 1 | **包 H** TUI 增强 | 需要包 E（会话检查点数据）和包 F（团队状态）都已合并 |

---

## 并行执行的集成风险：4 个 agent 会抢同样几个文件

**这是并行分工里最容易出问题的地方，必须显式处理，不能假设 4 个 agent 各写各的互不干扰。**

第 1 波四个包会同时修改这几个"公共登记点"：

| 文件 | 谁会改 | 冲突表现 |
|---|---|---|
| `core/runner.py::_build_registry()` | 包 B（注册 `tool_search`）、包 C（注册 `ask_user`）、包 D（注册 `exit_plan_mode`）、包 E（加检查点逻辑） | 4 个 agent 都在这个函数里加 `registry.register(...)`，同一处插入点必然产生 merge conflict |
| `core/permissions/policy.py::DEFAULT_POLICIES` | 包 B、包 C、包 D 都要给自己的新工具登记默认策略 | 同一个 dict 字面量被 3 个分支同时追加条目，是最常见的 diff 冲突模式 |
| `core/config.py` | 包 E（记忆相关配置项）可能与其他包在同一 dataclass 区域加字段 | 视具体字段位置而定，风险中等 |

**处理方式（按优先级）：**

1. **每个 agent 必须在独立 git worktree/分支里工作**，不要 4 个 agent 直接在同一个工作目录改代码——这正好是基础闭环计划 Task 8-9 刚做出来的 `enter_worktree` 能力，可以直接拿来给这 4 个 agent 分别开工作树。
2. **每一波结束后插入一个"集成任务"**（不算在 4 个 agent 的名额里，由你或我来做）：依次合并 4 个分支，手动解决 `_build_registry()` 和 `DEFAULT_POLICIES` 里的插入冲突（这两处冲突通常是"新增一行"级别，解决成本低，但必须人工过一遍，不能自动合并了事）。
3. 如果想从源头减少这类冲突，长期可以把 `_build_registry()` 从"一个函数里堆 N 个 register 调用"改成"每个工具模块自带注册函数、`runner.py` 只负责遍历调用"——但这是一次额外的重构，要不要现在做值得单独决定，不建议为了并行分工临时插进来，容易和 4 个包的改动互相打架。

---

## 每个 agent 拿到手上具体做什么

分工到人之后，**每个 agent 拿到的不是"包 X 做完"这么模糊的目标**，而是：

1. 先用 superpowers:writing-plans 把自己负责的包，从本文档"目标文件+关键设计点"的粒度，展开成和基础闭环计划同等细节的独立任务文件（`docs/superpowers/plans/2026-07-21-kama-agent-package-<b/c/d/e/f/g/h>.md`），每步要有完整代码、失败测试→实现→通过测试→commit。
2. 展开完的计划文件建议先给你过一眼再执行——尤其是包 D 和包 E，因为后面的包 F、包 H 直接依赖它们暴露的接口，接口定歪了下游要返工。
3. 执行时严格遵守仓库 `CLAUDE.md` 的中文注释规范（函数一行、测试两行"功能/设计"），这是所有 agent 共同的硬约束，不因为并行就放松。

需要我现在就把包 D 和包 E（第 1 波里两个互相不依赖、但下游都依赖它们的包）先展开成完整 TDD 计划吗？
