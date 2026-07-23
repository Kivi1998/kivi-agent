"""kivi-health: Python 入口调用 scripts/health_check.sh（Wave 7 WT-K1）。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HEALTH_SH = REPO_ROOT / "scripts" / "health_check.sh"


def main() -> int:
    """解析 --mode / --json / --quiet，转给 scripts/health_check.sh。

    返回：scripts/health_check.sh 的 exit code（0 = 全部健康；非 0 = 有失败项）。
    """
    parser = argparse.ArgumentParser(
        prog="kivi-health",
        description="kivi-agent 健康检查 (minimal|web|full)",
    )
    parser.add_argument(
        "--mode",
        choices=["minimal", "web", "full"],
        default="minimal",
        help="检查模式（默认 minimal）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--quiet", action="store_true", help="只输出失败项")
    args, extra = parser.parse_known_args()

    if not HEALTH_SH.exists():
        print(f"❌ 找不到健康检查脚本: {HEALTH_SH}", file=sys.stderr)
        return 1

    cmd: list[str] = [str(HEALTH_SH), "--mode", args.mode]
    if args.json:
        cmd.append("--json")
    if args.quiet:
        cmd.append("--quiet")
    cmd.extend(extra)

    result = subprocess.run(  # noqa: S603
        cmd,
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
