#!/usr/bin/env bash
# scripts/stop.sh — kivi-agent 停止（Wave 7 WT-K1）
# 功能：按 --mode 停对应 profile 的 services；缺省停全部
# 设计：
#   - 缺省 mode = all：把 3 个 profile 一起停（一次清干净）
#   - --volumes 同时删数据卷（ES / Redis / kivi-core 持久化）
#   - --rmi local 同时删本地构建的镜像（core/gateway/chatbox）
set -euo pipefail

MODE="all"
VOLUMES_FLAG=""
RMI_FLAG=""

usage() {
    cat <<'EOF'
用法: scripts/stop.sh [--mode minimal|web|full|all] [--volumes] [--rmi local]

模式：
  minimal  只停 minimal profile（core）
  web      停 minimal + web（core + gateway + chatbox）
  full     停 minimal + web + full（含 ES / Redis / evaluation-exporter）
  all      同 full（默认）

选项：
  --volumes    同时删除命名卷（es_data / redis_data / kivi-core-data）
  --rmi local  同时删除本地构建的镜像（kivi-agent-{core,gateway,chatbox}:wave7）
  -h, --help   显示本帮助

示例：
  scripts/stop.sh                          # 停全部（保留数据卷和镜像）
  scripts/stop.sh --mode minimal           # 只停 core
  scripts/stop.sh --volumes                # 停全部 + 清数据
  scripts/stop.sh --volumes --rmi local    # 全部清干净（重建前用）
EOF
}

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
        --volumes)
            VOLUMES_FLAG="--volumes"
            shift
            ;;
        --rmi)
            RMI_FLAG="--rmi $2"
            shift 2
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

case "$MODE" in
    minimal|web|full|all) ;;
    *)
        echo "❌ --mode 必须是 minimal / web / full / all，收到: $MODE" >&2
        exit 1
        ;;
esac

if ! command -v docker >/dev/null 2>&1; then
    echo "❌ docker 未安装" >&2
    exit 1
fi

# ---- 计算要停的 profile 集合 ----
PROFILES=()
case "$MODE" in
    minimal)
        PROFILES=(--profile minimal)
        ;;
    web)
        PROFILES=(--profile minimal --profile web)
        ;;
    full|all)
        PROFILES=(--profile minimal --profile web --profile full)
        ;;
esac

echo "🛑 停止 kivi-agent (mode=$MODE)..."

# shellcheck disable=SC2086
docker compose "${PROFILES[@]}" down $VOLUMES_FLAG $RMI_FLAG

echo "✅ 停止完成（mode=$MODE volumes=${VOLUMES_FLAG:-no} rmi=${RMI_FLAG:-no}）"
