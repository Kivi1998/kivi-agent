#!/usr/bin/env bash
# scripts/health_check.sh — kivi-agent 多组件健康检查（Wave 7 WT-K1）
# 功能：按 --mode 探测 core / gateway / chatbox / elasticsearch / redis 状态
# 设计：
#   - 每个组件用 curl / redis-cli / docker compose ps 三种方式之一
#   - 退出码：0 = 全部 OK；1 = 至少一项失败
#   - --json 输出结构化报告（CI 用）；--quiet 只输出失败项
set -euo pipefail

MODE="minimal"
JSON_FLAG=""
QUIET_FLAG=""

# 报告缓冲
REPORT_LINES=()
FAILED=0

usage() {
    cat <<'EOF'
用法: scripts/health_check.sh [--mode minimal|web|full] [--json] [--quiet]

模式：
  minimal  检查 core（7437）
  web      minimal + gateway (8000) + chatbox (5173)
  full     web + elasticsearch (9200) + redis (6379) + evaluation-exporter

选项：
  --json   输出 JSON 格式（CI 用）
  --quiet  只输出失败项
  -h, --help  显示本帮助

示例：
  scripts/health_check.sh                   # minimal 检查
  scripts/health_check.sh --mode web        # web 检查
  scripts/health_check.sh --mode full --json  # full 检查 + JSON
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
        --json)
            JSON_FLAG=1
            shift
            ;;
        --quiet)
            QUIET_FLAG=1
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

case "$MODE" in
    minimal|web|full) ;;
    *)
        echo "❌ --mode 必须是 minimal / web / full，收到: $MODE" >&2
        exit 1
        ;;
esac

# ---- 检查函数 ----

# 用 docker compose ps 判断容器是否 healthy
# 用法：check_container <service> <expected_status>   expected_status: running | healthy
check_container() {
    local service="$1"
    local expected="$2"
    local actual
    local state
    # 选 minimal+web+full 全部 profile，确保能查到
    actual=$(docker compose --profile minimal --profile web --profile full ps --format json "$service" 2>/dev/null || true)
    if [[ -z "$actual" ]]; then
        _report "$service" "container" "down" "容器未运行"
        return 1
    fi
    # 用 python 解析 JSON 拿 State 字段（更稳）
    state=$(echo "$actual" | python3 -c 'import json, sys
try:
    data = json.loads(sys.stdin.read())
    if isinstance(data, list) and data:
        print(data[0].get("State", "unknown"))
    else:
        print("unknown")
except Exception:
    print("unknown")' 2>/dev/null || echo "unknown")
    if [[ "$state" == "$expected" || "$state" == "running" && "$expected" == "healthy" ]]; then
        _report "$service" "container" "up" "state=$state"
        return 0
    fi
    _report "$service" "container" "degraded" "state=$state (expected $expected)"
    return 1
}

# 用 curl 检查 HTTP 端点
# 用法：check_http <service> <url>
check_http() {
    local service="$1"
    local url="$2"
    local code
    code=$(curl -fsS -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")
    if [[ "$code" =~ ^2 ]]; then
        _report "$service" "http" "up" "$url → $code"
        return 0
    fi
    _report "$service" "http" "down" "$url → $code"
    return 1
}

# 用 redis-cli ping 检查
check_redis() {
    local container="${1:-kivi-agent-redis}"
    if docker exec "$container" redis-cli ping 2>/dev/null | grep -q PONG; then
        _report "redis" "ping" "up" "PONG"
        return 0
    fi
    _report "redis" "ping" "down" "无 PONG 响应"
    return 1
}

# 报告写入缓冲
_report() {
    local name="$1"
    local kind="$2"
    local status="$3"
    local detail="$4"
    if [[ "$status" == "up" ]]; then
        REPORT_LINES+=("{\"component\":\"$name\",\"check\":\"$kind\",\"status\":\"$status\",\"detail\":\"$detail\"}")
    else
        REPORT_LINES+=("{\"component\":\"$name\",\"check\":\"$kind\",\"status\":\"$status\",\"detail\":\"$detail\"}")
        FAILED=$((FAILED + 1))
    fi
}

# 打印 human 报告
print_human() {
    if [[ -n "$QUIET_FLAG" && $FAILED -eq 0 ]]; then
        return
    fi
    echo "=== kivi-agent health (mode=$MODE) ==="
    for line in "${REPORT_LINES[@]}"; do
        # 简单解析回 human
        status=$(echo "$line" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); print(d["status"])' 2>/dev/null)
        component=$(echo "$line" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); print(d["component"])' 2>/dev/null)
        detail=$(echo "$line" | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); print(d["detail"])' 2>/dev/null)
        case "$status" in
            up)      echo "  ✅ $component: $detail" ;;
            down|degraded) echo "  ❌ $component: $detail" ;;
        esac
    done
    if [[ $FAILED -eq 0 ]]; then
        echo "  → 全部健康"
    else
        echo "  → $FAILED 项异常"
    fi
}

# 打印 JSON 报告
print_json() {
    local joined
    joined=$(printf '%s,' "${REPORT_LINES[@]}")
    echo "{\"mode\":\"$MODE\",\"failed\":$FAILED,\"checks\":[${joined%,}]}"
}

# ---- 主流程 ----
echo "🔍 检查 kivi-agent 健康 (mode=$MODE)..."

# minimal 必查：core
check_container "core" "healthy" || true

# web 加查：gateway + chatbox
if [[ "$MODE" == "web" || "$MODE" == "full" ]]; then
    check_container "gateway" "healthy" || true
    check_container "chatbox-frontend" "healthy" || true
    # 端口可达性二次确认（即使容器 healthy，端口可能未暴露）
    check_http "core" "http://127.0.0.1:7437/health" || true   # core 不一定有 /health，跳过失败
    check_http "gateway" "http://127.0.0.1:8000/health" || true
    check_http "chatbox" "http://127.0.0.1:5173/" || true
fi

# full 加查：ES + Redis + evaluation-exporter
if [[ "$MODE" == "full" ]]; then
    check_container "elasticsearch" "healthy" || true
    check_container "redis" "healthy" || true
    check_container "evaluation-exporter" "running" || true
    check_http "elasticsearch" "http://127.0.0.1:9200/_cluster/health" || true
    check_redis "kivi-agent-redis" || true
fi

# ---- 输出 ----
if [[ -n "$JSON_FLAG" ]]; then
    print_json
else
    print_human
fi

exit $FAILED
