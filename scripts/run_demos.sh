#!/usr/bin/env bash
# run_demos.sh: 顺序跑 5 个 demo + 输出汇总报告（agent: package-demo-v7）
# 用法: scripts/run_demos.sh [--env-guard] [--no-fail]
#   --env-guard: 用 KIVI_RUN_DEMOS=1 守卫（默认开启）
#   --no-fail: 即使有 demo 失败也 exit 0
set -e

# ---- 参数解析 ----
ENV_GUARD=1
NO_FAIL=0
for arg in "$@"; do
    case "$arg" in
        --no-fail) NO_FAIL=1 ;;
        --no-env-guard) ENV_GUARD=0 ;;
        --env-guard) ENV_GUARD=1 ;;
        *) echo "[run_demos] unknown arg: $arg"; exit 2 ;;
    esac
done

# ---- 守卫：KIVI_RUN_DEMOS 必须显式设置 ----
if [[ "$ENV_GUARD" -eq 1 && "${KIVI_RUN_DEMOS:-}" != "1" ]]; then
    echo "[run_demos] SKIP: KIVI_RUN_DEMOS != 1 (export KIVI_RUN_DEMOS=1 to run)"
    exit 0
fi

# ---- 解析项目根（脚本所在目录的上 1 级）----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

mkdir -p reports

# ---- 跑 5 个 demo ----
DEMOS=(
    "demo1_coding"
    "demo2_rag"
    "demo3_database"
    "demo4_frontend_map"
    "demo5_multi_agent"
)

PASS_COUNT=0
FAIL_COUNT=0
START_TS=$(date +%s)
echo "[run_demos] running ${#DEMOS[@]} demos at $(date -u +%Y-%m-%dT%H:%M:%SZ)"

for demo in "${DEMOS[@]}"; do
    if uv run python -m "demos.${demo}" 2>&1 | tail -1; then
        if [[ -f "reports/demo_${demo}.json" ]]; then
            STATUS=$(python3 -c "import json; d=json.load(open('reports/demo_${demo}.json')); print(d['status'])")
            if [[ "$STATUS" == "passed" ]]; then
                PASS_COUNT=$((PASS_COUNT + 1))
            else
                FAIL_COUNT=$((FAIL_COUNT + 1))
            fi
        fi
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "[✗] ${demo} FAILED (no report)"
    fi
done

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

# ---- 汇总 ----
SUMMARY_FILE="reports/demos_summary.json"
python3 - <<PY
import json, glob, os
results = []
for path in sorted(glob.glob("reports/demo_*.json")):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    results.append({
        "name": d["name"],
        "status": d["status"],
        "summary": d["summary"],
        "duration_seconds": d["duration_seconds"],
    })
total = len(results)
passed = sum(1 for r in results if r["status"] == "passed")
failed = sum(1 for r in results if r["status"] == "failed")
summary = {
    "total": total,
    "passed": passed,
    "failed": failed,
    "all_passed": failed == 0 and passed == total,
    "results": results,
    "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "duration_seconds": $DURATION,
}
with open("$SUMMARY_FILE", "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

echo
echo "[run_demos] DONE: passed=${PASS_COUNT} failed=${FAIL_COUNT} duration=${DURATION}s"

# ---- 退出码 ----
if [[ "$FAIL_COUNT" -eq 0 ]]; then
    exit 0
fi
if [[ "$NO_FAIL" -eq 1 ]]; then
    exit 0
fi
exit 1
