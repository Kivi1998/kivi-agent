"""敏感信息过滤器（Wave 6.1 J2 增强）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TypedDict


# 单次过滤结果。
class FilteredResult(TypedDict):
    safe: bool  # 文本是否完全安全（无任何敏感命中）。
    sanitized: str  # 脱敏后的文本。
    warnings: list[str]  # 命中类型描述列表。


# 密码 / API key / token / secret / private_key 形如 key=value 或 key: value，
# value 至少 1 个非空白字符。
# group(1) = key 名称；group(2) = 整体匹配（key+分隔+value）。
# value 类允许常见 base64 / hex / PEM 字符（含 - _ / = + . ），
# 不含空白与常见语句终止符；
# 引号本身不排除，因为值常被 "" 或 '' 包裹。
_SENSITIVE_KV_RE = re.compile(
    r"(?i)(\b(?:password|api_key|apikey|token|secret|private_key|passwd|pwd)\b)"
    r"\s*[:=]\s*"
    r"([^\s,;`<>|\\()]+)"
)

# 中国大陆手机号：1 开头 11 位数字；与行边界相邻。
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

# 邮箱地址：基础模式，覆盖常见 ascii 邮箱。
_EMAIL_RE = re.compile(
    r"(?<![A-Za-z0-9._%+-])"
    r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
    r"(?![A-Za-z0-9._%+-])"
)

# 中国大陆身份证号：18 位（末位可为 x/X）或 15 位（旧版）。
_IDCARD_RE = re.compile(r"(?<!\d)(\d{17}[\dXx]|\d{15})(?!\d)")

# Bearer / Basic / Token 开头的鉴权头。
_AUTH_HEADER_RE = re.compile(
    r"(?i)\b(bearer|basic)\s+([A-Za-z0-9._\-+/=]{8,})"
)

# 替换占位符：保留键名 + 冒号/等号，把值换成 ***，让人类仍能识别原始结构。
_REDACTED_VALUE = "***REDACTED***"


@dataclass
class SensitiveInfoFilter:
    """敏感信息过滤器：扫描文本中的密码 / key / 手机 / 邮箱 / 身份证，返回脱敏结果。"""

    redact_phone: bool = True  # 是否对手机号脱敏。
    redact_email: bool = True  # 是否对邮箱脱敏。
    redact_idcard: bool = True  # 是否对身份证脱敏。
    redact_auth_header: bool = True  # 是否对 Authorization/Bearer 头脱敏。
    _extra_patterns: list[re.Pattern[str]] = field(default_factory=list)

    def add_pattern(self, pattern: re.Pattern[str]) -> None:
        """注册额外正则；命中后会把整段 match 替换为占位符。"""
        self._extra_patterns.append(pattern)

    # 扫描 + 替换，返回 FilteredResult；命中任一规则即 safe=False，但永远不抛异常。
    def filter(self, text: str) -> FilteredResult:
        if not text:
            return FilteredResult(safe=True, sanitized=text, warnings=[])
        warnings: list[str] = []
        sanitized = text

        sanitized, kv_warns = self._mask_kv(sanitized)
        warnings.extend(kv_warns)

        if self.redact_phone:
            sanitized, phone_warns = self._mask_full(sanitized, _PHONE_RE, "phone")
            warnings.extend(phone_warns)
        if self.redact_email:
            sanitized, email_warns = self._mask_full(sanitized, _EMAIL_RE, "email")
            warnings.extend(email_warns)
        if self.redact_idcard:
            sanitized, id_warns = self._mask_full(sanitized, _IDCARD_RE, "idcard")
            warnings.extend(id_warns)
        if self.redact_auth_header:
            sanitized, auth_warns = self._mask_auth(sanitized)
            warnings.extend(auth_warns)

        for pat in self._extra_patterns:
            sanitized, extra_warns = self._mask_full(sanitized, pat, "custom")
            warnings.extend(extra_warns)

        return FilteredResult(
            safe=len(warnings) == 0,
            sanitized=sanitized,
            warnings=warnings,
        )

    # 把 key=value 整体替换为 key=***，保留原始 key 名便于人类阅读。
    def _mask_kv(self, text: str) -> tuple[str, list[str]]:
        warns: list[str] = []

        def _repl(match: re.Match[str]) -> str:
            key = match.group(1)
            warns.append(f"credential:{key.lower()}")
            return f"{key}={_REDACTED_VALUE}"

        new_text = _SENSITIVE_KV_RE.sub(_repl, text)
        return new_text, warns

    # 整段 match 替换为占位符。
    def _mask_full(
        self, text: str, pattern: re.Pattern[str], kind: str
    ) -> tuple[str, list[str]]:
        warns: list[str] = []

        def _repl_default(match: re.Match[str]) -> str:
            warns.append(kind)
            return _REDACTED_VALUE

        new_text = pattern.sub(_repl_default, text)
        return new_text, warns

    # 鉴权头：保留 scheme + 空格，value 替换。
    def _mask_auth(self, text: str) -> tuple[str, list[str]]:
        warns: list[str] = []

        def _repl_auth(match: re.Match[str]) -> str:
            scheme = match.group(1)
            warns.append(f"auth_header:{scheme.lower()}")
            return f"{scheme} {_REDACTED_VALUE}"

        new_text = _AUTH_HEADER_RE.sub(_repl_auth, text)
        return new_text, warns
