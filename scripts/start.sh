#!/usr/bin/env bash
# scripts/start.sh — kivi-agent 多模式启动（Wave 7 WT-K1）
# 功能：按 --mode minimal|web|full 调用 docker compose 对应 profile
# 设计：
#   - 缺省 --mode = minimal（最安全启动）
#   - 自动 cp .env.example .env（如不存在）
#   - --build 强制重建镜像；--wait 等所有 healthy
#   - set -euo pipefail：任一失败即停
set -euo pipefail

# ---- 默认参数 ----
MODE="minimal"
BUILD_FLAG=""
WAIT_FLAG=""
COMPOSE_FILE="docker-compose.yml"

# ---- 用法 ----
usage() {
    cat <<'EOF'
用法: scripts/start.sh [--mode minimal|web|full] [--build] [--wait]

模式：
  minimal  只起 kivi-core 守护进程（无外部依赖）
  web      minimal + kivi-gateway + chatbox-frontend
  full     web + elasticsearch + redis + evaluation-exporter

选项：
  --build  强制重建镜像（修改 Dockerfile 后用）
  --wait   等所有 healthcheck 通过才返回（默认不等）
  -h, --help  显示本帮助

示例：
  scripts/start.sh                     # minimal 模式
  scripts/start.sh --mode web          # web 模式
  scripts/start.sh --mode full --build # full 模式 + 重建镜像
EOF
}

# ---- 解析参数 ----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode)
            MODE="$2"
            shift 2
            ;;
        --mode=*)
            MODE="${1#*=}"
            shift
            ;;
        --build)
            BUILD_FLAG="--build"
            shift
            ;;
        --wait)
            WAIT_FLAG="--wait"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "❌ 未知参数: $1" >&2
            usage
            exit 1
            ;;
    esac
done

# ---- 校验 mode ----
case "$MODE" in
    minimal|web|full) ;;
    *)
        echo "❌ --mode 必须是 minimal / web / full，收到: $MODE" >&2
        exit 1
        ;;
esac

# ---- 校验 docker ----
if ! command -v docker >/dev/null 2>&1; then
    echo "❌ docker 未安装或不在 PATH" >&2
    exit 1
fi

# ---- 检查 .env ----
if [[ ! -f .env ]]; then
    if [[ -f .env.example ]]; then
        echo "ℹ️  .env 不存在，从 .env.example 复制（请按需修改）"
        cp .env.example .env
    else
        echo "❌ .env 与 .env.example 都不存在" >&2
        exit 1
    fi
fi

# ---- 启动 ----
echo "🚀 启动 kivi-agent ($MODE 模式)..."
PROFILE_FLAG="--profile $MODE"
if [[ "$MODE" == "web" ]]; then
    # web 模式需要 minimal 的 core + web/gateway + chatbox
    # 但 profile 之间是 union 关系：--profile web 会自动包含 minimal
    PROFILE_FLAG="--profile web"
elif [[ "$MODE" == "full" ]]; then
    PROFILE_FLAG="--profile full"
fi

# shellcheck disable=SC2086
docker compose -f "$COMPOSE_FILE" $PROFILE_FLAG up -d $BUILD_FLAG

if [[ -n "$WAIT_FLAG" ]]; then
    echo "⏳ 等待 healthcheck 通过..."
    # shellcheck disable=SC2086
    docker compose -f "$COMPOSE_FILE" $PROFILE_FLAG wait
fi

echo "✅ 启动完成（mode=$MODE build=${BUILD_FLAG:-no} wait=${WAIT_FLAG:-no}）"
echo "💡 健康检查: scripts/health_check.sh --mode $MODE"
echo "💡 停止服务: scripts/stop.sh --mode $MODE"
