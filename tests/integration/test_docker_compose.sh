#!/usr/bin/env bash
# tests/integration/test_docker_compose.sh — 3 模式 Docker Compose 集成测试（Wave 7 WT-K1）
# 功能：起 minimal / web / full 三个 profile 的 services，验证 healthcheck 通过
# 设计：
#   - 用 KIVI_RUN_DOCKER_TESTS=1 守护（避免 CI 默认跑 docker）
#   - 每个模式独立测试：up → health_check → down
#   - 失败不污染：set -e + trap 清理
#   - 报告每模式耗时 + 通过/失败，结尾汇总
set -euo pipefail

# ---- 守护 ----
if [[ "${KIVI_RUN_DOCKER_TESTS:-0}" != "1" ]]; then
    echo "⏭  跳过（设 KIVI_RUN_DOCKER_TESTS=1 启用）"
    exit 0
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

# 颜色（仅当 TTY）
if [[ -t 1 ]]; then
    GREEN="\033[32m"
    RED="\033[31m"
    YELLOW="\033[33m"
    RESET="\033[0m"
else
    GREEN=""
    RED=""
    YELLOW=""
    RESET=""
fi

# 预检
command -v docker >/dev/null 2>&1 || { echo "❌ docker 未安装" >&2; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo "❌ docker compose plugin 未安装" >&2; exit 1; }

# 准备 .env
if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "ℹ️  已从 .env.example 创建 .env"
fi

# 报告缓冲
RESULTS=()
FAILED=0

# 测试一个模式
# 用法：run_test <mode> <max_wait_s>
run_test() {
    local mode="$1"
    local max_wait="${2:-180}"
    local start_ts end_ts elapsed
    start_ts=$(date +%s)

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🧪 测试模式: $mode (最长 ${max_wait}s)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 启动
    if ! ./scripts/start.sh --mode "$mode" --build; then
        echo "  ❌ start.sh --mode $mode 失败"
        RESULTS+=("$mode:FAIL(启动)")
        FAILED=$((FAILED + 1))
        ./scripts/stop.sh --mode "$mode" --volumes --rmi local 2>/dev/null || true
        return 1
    fi

    # 等 healthcheck（轮询 health_check.sh）
    local waited=0
    local healthy=0
    while [[ $waited -lt $max_wait ]]; do
        if ./scripts/health_check.sh --mode "$mode" --quiet >/dev/null 2>&1; then
            healthy=1
            break
        fi
        sleep 5
        waited=$((waited + 5))
        echo "  ⏳ 等待 healthcheck ... ${waited}s / ${max_wait}s"
    done

    if [[ $healthy -eq 0 ]]; then
        echo "  ❌ healthcheck 超时（>${max_wait}s）"
        ./scripts/health_check.sh --mode "$mode" || true   # 打印失败详情
        RESULTS+=("$mode:FAIL(health 超时)")
        FAILED=$((FAILED + 1))
        ./scripts/stop.sh --mode "$mode" --volumes --rmi local 2>/dev/null || true
        return 1
    fi

    # 健康检查详情
    ./scripts/health_check.sh --mode "$mode"
    echo "  ✅ health 通过"

    # 关闭
    if ! ./scripts/stop.sh --mode "$mode" --volumes --rmi local; then
        echo "  ⚠️  stop.sh 清理失败（不影响测试结果）"
    fi

    end_ts=$(date +%s)
    elapsed=$((end_ts - start_ts))
    RESULTS+=("$mode:PASS(${elapsed}s)")
    return 0
}

# 清理函数（异常退出时跑）
cleanup() {
    echo ""
    echo "🧹 异常清理：停止所有 profile"
    ./scripts/stop.sh --mode all --volumes --rmi local 2>/dev/null || true
}
trap cleanup EXIT

# ---- 跑 3 个模式 ----
# 注：每个测试独立跑，全跑耗时较长；CI 上可加 KIVI_RUN_DOCKER_TESTS_FAST=1 跳 full
if [[ "${KIVI_RUN_DOCKER_TESTS_FAST:-0}" != "1" ]]; then
    run_test minimal 120 || true
    run_test web 180 || true
    run_test full 240 || true
else
    echo "ℹ️  KIVI_RUN_DOCKER_TESTS_FAST=1：只跑 minimal"
    run_test minimal 120 || true
fi

# ---- 汇总 ----
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 汇总"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
for r in "${RESULTS[@]}"; do
    if [[ "$r" == *":PASS"* ]]; then
        echo -e "  ${GREEN}✅${RESET} $r"
    else
        echo -e "  ${RED}❌${RESET} $r"
    fi
done

if [[ $FAILED -gt 0 ]]; then
    echo -e "${RED}❌ $FAILED 项失败${RESET}"
    exit 1
fi

echo -e "${GREEN}✅ 全部通过${RESET}"
exit 0
