from __future__ import annotations

import shlex


class BwrapSandbox:
    # 用 Linux bubblewrap 包装命令：根文件系统只读挂载，allow_write 里的目录改为可写 bind，可选禁网
    def wrap(self, command: str, *, allow_write: list[str], network: bool = False) -> str:
        args = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc"]
        for path in allow_write:
            args.extend(["--bind", path, path])
        if not network:
            args.append("--unshare-net")
        args.extend(["bash", "-c", command])
        return " ".join(shlex.quote(a) if " " in a else a for a in args)
