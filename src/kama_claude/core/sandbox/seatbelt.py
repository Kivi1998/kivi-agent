from __future__ import annotations

import shlex


class SeatbeltSandbox:
    # 用 macOS sandbox-exec 包装命令：默认拒绝一切，显式放行只读、指定目录可写和可选网络
    def wrap(self, command: str, *, allow_write: list[str], network: bool = False) -> str:
        write_rules = "\n".join(
            f'(allow file-write* (subpath "{path}"))' for path in allow_write
        )
        network_rule = "(allow network*)" if network else ""
        profile = f"""(version 1)
(deny default)
(allow file-read*)
{write_rules}
{network_rule}
(allow process-fork)
(allow process-exec)
"""
        return f"/usr/bin/sandbox-exec -p {shlex.quote(profile)} bash -c {shlex.quote(command)}"
