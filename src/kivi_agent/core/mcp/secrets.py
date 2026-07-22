from __future__ import annotations

import logging
import os
import re

log = logging.getLogger(__name__)

_SECRET_REF_RE = re.compile(r"^\$\{SECRET:([A-Za-z_][A-Za-z0-9_]*)\}$")


# 把形如 "${SECRET:NAME}" 的值替换为对应环境变量的真实值；未设置的环境变量替换为空字符串
def resolve_secret_refs(env: dict[str, str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for key, value in env.items():
        match = _SECRET_REF_RE.match(value)
        if match is None:
            resolved[key] = value
            continue
        var_name = match.group(1)
        actual = os.environ.get(var_name)
        if actual is None:
            log.warning("mcp secret reference unresolved: %s -> $%s not set", key, var_name)
            actual = ""
        resolved[key] = actual
    return resolved
