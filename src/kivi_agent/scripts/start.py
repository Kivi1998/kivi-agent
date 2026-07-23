"""kivi-start: Python 入口调用 scripts/start.sh（Wave 7 WT-K1）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# repo 根 = src/kivi_agent/scripts/start.py 的 ../../..
REPO_ROOT = Path(__file__).resolve().parents[3]
START_SH = REPO_ROOT / "scripts" / "start.sh"


def main() -> int:
    """解析 --mode / --build / --wait，转给 scripts/start.sh。

    返回：scripts/start.sh 的 exit code（0 = 成功）。
    """
    parser = argparse.ArgumentParser(
        prog="kivi-start",
        description="启动 kivi-agent (minimal|web|full profile)",
    )
    parser.add_argument(
        "--mode",
        choices=["minimal", "web", "full"],
        default="minimal",
        help="启动模式（默认 minimal）",
    )
    parser.add_argument("--build", action="store_true", help="强制重建镜像")
    parser.add_argument("--wait", action="store_true", help="等所有 healthcheck 通过")
    args, extra = parser.parse_known_args()

    if not START_SH.exists():
        print(f"❌ 找不到启动脚本: {START_SH}", file=sys.stderr)
        return 1

    # 用当前 Python 进程 + shell 脚本直传 stdout/stderr
    import subprocess

    cmd: list[str] = [str(START_SH), "--mode", args.mode]
    if args.build:
        cmd.append("--build")
    if args.wait:
        cmd.append("--wait")
    cmd.extend(extra)

    # 让 shell 脚本在仓库根执行（脚本假设 PWD = repo root）
    result = subprocess.run(  # noqa: S603
        cmd,
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
