# mewcode 迁移许可说明

- mewcode（`/Users/kivi/Documents/agent系统/mewcode`）根目录未发现 LICENSE 文件，来源和授权条款不明确。
- 因此本次迁移（工作分支 `feat/kama-agent-minimal-loop`）只参考 mewcode 的设计思路和公开算法（如 glob/grep 的过滤策略、edit_file 的唯一匹配替换逻辑、diff 的展示格式、Git 工作树生命周期管理、macOS/Linux 沙箱的系统机制选型），所有代码在 KamaClaude 仓库中用自己的类型系统、工具基类和错误处理约定独立实现。
- 不直接复制、粘贴 mewcode 的任何源码文件。
- 如后续需要更大范围迁移（企业级整合方案中的 M01~M44），必须先取得 mewcode 明确的许可声明或改为完全独立重写。
