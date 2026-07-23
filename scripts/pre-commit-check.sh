#!/usr/bin/env bash
# scripts/pre-commit-check.sh — 防止 .env / 真 API key 被 commit 的本地预检（Wave 7 WT-K1）
# 功能：在 git commit 前扫描待提交内容，命中真 key 模式则拒绝
# 设计：本地脚本（不依赖 git hooks 框架），可手动 `bash scripts/pre-commit-check.sh` 或接入 pre-commit 框架
set -euo pipefail

# 检查项 1：.env 不能被追踪
if git ls-files --error-unmatch .env 2>/dev/null; then
    echo "❌ .env 被 git 追踪！请先执行：git rm --cached .env" >&2
    exit 1
fi

# 检查项 2：本次待提交内容不能含真 API key（placeholder / 注释除外）
# 真 key 匹配模式：sk-ant-... 32+ 字符 / sk- 后续 32+ 字符 / Bearer sk-...
LEAKED=$(git diff --cached -U0 | grep -E "^\+" | grep -E "(sk-ant-[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{32,}|Bearer sk-)" || true)
if [ -n "$LEAKED" ]; then
    echo "❌ 检测到真 API key 模式，禁止提交：" >&2
    echo "$LEAKED" >&2
    exit 1
fi

# 检查项 3：.env 路径不出现在本次新增文件里
ADDED_ENV=$(git diff --cached --name-only --diff-filter=A | grep -E "^\.env(\.|$)" | grep -v "^\.env\.example$" || true)
if [ -n "$ADDED_ENV" ]; then
    echo "❌ 新增了 .env* 文件但不是 .env.example：$ADDED_ENV" >&2
    exit 1
fi

echo "✅ pre-commit-check 通过：未检测到 .env 追踪 / 真 API key 泄露"
