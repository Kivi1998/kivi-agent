"""kivi-stop: Python 入口调用 scripts/stop.sh（Wave 7 WT-K1）。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
STOP_SH = REPO_ROOT / "scripts" / "stop.sh"


def main() -> int:
    """解析 --mode / --volumes / --rmi，转给 scripts/stop.sh。

    返回：scripts/stop.sh 的 exit code（0 = 成功）。
    """
    parser = argparse.ArgumentParser(
        prog="kivi-stop",
        description="停止 kivi-agent (minimal|web|full|all profile)",
    )
    parser.add_argument(
        "--mode",
        choices=["minimal", "web", "full", "all"],
        default="all",
        help="停止模式（默认 all = 全部 profile）",
    )
    parser.add_argument("--volumes", action="store_true", help="同时删除命名卷")
    parser.add_argument(
        "--rmi",
        choices=["local"],
        default=None,
        help="同时删除本地构建镜像（仅支持 local）",
    )
    args, extra = parser.parse_known_args()

    if not STOP_SH.exists():
        print(f"❌ 找不到停止脚本: {STOP_SH}", file=sys.stderr)
        return 1

    cmd: list[str] = [str(STOP_SH), "--mode", args.mode]
    if args.volumes:
        cmd.append("--volumes")
    if args.rmi:
        cmd.extend(["--rmi", args.rmi])
    cmd.extend(extra)

    result = subprocess.run(  # noqa: S603
        cmd,
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
