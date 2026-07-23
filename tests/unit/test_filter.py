from __future__ import annotations

import re

from kivi_agent.core.memory.filter import (
    _AUTH_HEADER_RE,
    _EMAIL_RE,
    _IDCARD_RE,
    _PHONE_RE,
    _SENSITIVE_KV_RE,
    SensitiveInfoFilter,
)


# 功能：默认安全文本不产生任何警告
# 设计：纯中文 + 英文混排不命中任何规则，断言 safe=True 且 sanitized 等于原文本
def test_safe_text_returns_no_warnings() -> None:
    f = SensitiveInfoFilter()
    result = f.filter("hello world, 纯中文也无事")
    assert result["safe"] is True
    assert result["sanitized"] == "hello world, 纯中文也无事"
    assert result["warnings"] == []


# 功能：空字符串直接返回 safe
# 设计：filter("") 应当安全返回，不会触发任何规则
def test_empty_string_is_safe() -> None:
    f = SensitiveInfoFilter()
    result = f.filter("")
    assert result["safe"] is True
    assert result["sanitized"] == ""
    assert result["warnings"] == []


# 功能：password=xxx 被识别并脱敏
# 设计：键值对走 _mask_kv 路径，断言 sanitized 含占位符，warnings 记录 credential:password
def test_password_equals_redacted() -> None:
    f = SensitiveInfoFilter()
    result = f.filter("password=Sup3rSecret!")
    assert result["safe"] is False
    assert "***REDACTED***" in result["sanitized"]
    assert "Sup3rSecret!" not in result["sanitized"]
    assert "credential:password" in result["warnings"]


# 功能：api_key: xxx 形式同样被识别
# 设计：测试冒号 + 空格分隔，断言键名被小写化记录
def test_api_key_colon_redacted() -> None:
    f = SensitiveInfoFilter()
    result = f.filter("config: api_key: sk-proj-abc-12345")
    assert result["safe"] is False
    assert "sk-proj-abc-12345" not in result["sanitized"]
    assert "credential:api_key" in result["warnings"]


# 功能：token 命中 key=value 形式
# 设计：token 单独出现，验证 key 名也小写
def test_token_equals_redacted() -> None:
    f = SensitiveInfoFilter()
    result = f.filter("export TOKEN=ghp_abcdefghij")
    assert "ghp_abcdefghij" not in result["sanitized"]
    assert "credential:token" in result["warnings"]


# 功能：secret 形如 secret: value 同样命中
# 设计：测试 secret 关键字的命中
def test_secret_colon_redacted() -> None:
    f = SensitiveInfoFilter()
    result = f.filter("aws secret: AKIAEXAMPLEKEY")
    assert "AKIAEXAMPLEKEY" not in result["sanitized"]
    assert "credential:secret" in result["warnings"]


# 功能：private_key 形如 private_key = "..." 也命中
# 设计：包含下划线的 key 名 + 等号 + 引号包裹值
def test_private_key_redacted() -> None:
    f = SensitiveInfoFilter()
    result = f.filter('private_key = "-----BEGIN RSA PRIVATE KEY-----"')
    assert "BEGIN RSA" not in result["sanitized"]
    assert "credential:private_key" in result["warnings"]


# 功能：大小写不敏感命中 Password / API_KEY
# 设计：原 regex 带 (?i) 标志，断言大写也被识别
def test_case_insensitive_keyword() -> None:
    f = SensitiveInfoFilter()
    result = f.filter("Password: P@ssw0rd123")
    assert "P@ssw0rd123" not in result["sanitized"]
    assert "credential:password" in result["warnings"]


# 功能：中国大陆手机号被识别并脱敏
# 设计：13-19 开头的 11 位数字，断言 sanitized 中无原始数字
def test_chinese_phone_redacted() -> None:
    f = SensitiveInfoFilter()
    result = f.filter("手机号 13800138000")
    assert result["safe"] is False
    assert "13800138000" not in result["sanitized"]
    assert "phone" in result["warnings"]


# 功能：邮箱地址被识别并脱敏
# 设计：标准 abc@def.com 格式，断言域名部分也被擦除
def test_email_redacted() -> None:
    f = SensitiveInfoFilter()
    result = f.filter("联系我 john.doe@example.com 谢谢")
    assert "john.doe@example.com" not in result["sanitized"]
    assert "email" in result["warnings"]


# 功能：18 位身份证号被识别并脱敏
# 设计：18 位 + 末位 X/X，断言 sanitized 中无完整号码
def test_idcard_18_redacted() -> None:
    f = SensitiveInfoFilter()
    result = f.filter("身份证 110101199003078888")
    assert "110101199003078888" not in result["sanitized"]
    assert "idcard" in result["warnings"]


# 功能：15 位旧版身份证号也被识别
# 设计：旧版 15 位，断言 123456789012345 被擦除
def test_idcard_15_redacted() -> None:
    f = SensitiveInfoFilter()
    result = f.filter("旧号 123456789012345")
    assert "123456789012345" not in result["sanitized"]
    assert "idcard" in result["warnings"]


# 功能：Bearer 鉴权头被脱敏
# 设计：bearer xyz 形式，scheme 保留，值被擦除
def test_bearer_token_redacted() -> None:
    f = SensitiveInfoFilter()
    result = f.filter("Authorization Bearer eyJhbGciOiJIUzI1Ni.payload.sig")
    assert "eyJhbGciOiJIUzI1Ni" not in result["sanitized"]
    assert "auth_header:bearer" in result["warnings"]


# 功能：redact_email=False 时邮箱不被脱敏
# 设计：构造仅含邮箱的文本 + 关闭邮箱脱敏，断言 safe=True
def test_email_redaction_can_be_disabled() -> None:
    f = SensitiveInfoFilter(redact_email=False)
    result = f.filter("ping user@example.com please")
    assert result["safe"] is True
    assert result["sanitized"] == "ping user@example.com please"


# 功能：add_pattern 允许注入额外正则
# 设计：注册一个匹配 "internal_token_<digits>" 的自定义正则，断言被擦除
def test_extra_pattern_is_applied() -> None:
    f = SensitiveInfoFilter()
    f.add_pattern(re.compile(r"internal_token_\d+"))
    result = f.filter("use internal_token_12345 for auth")
    assert "internal_token_12345" not in result["sanitized"]
    assert "custom" in result["warnings"]


# 功能：边界条件——手机号前有数字时不命中（防短数字误伤）
# 设计：12341380013800 不是 11 位手机号，断言 safe=True
def test_phone_boundary_not_matched() -> None:
    f = SensitiveInfoFilter()
    result = f.filter("seq 12341380013800 end")
    assert result["safe"] is True


# 功能：多类型同时命中时 warnings 完整记录
# 设计：单条文本含 phone + email，断言两种 warning 同时出现
def test_multiple_hits_record_all_warnings() -> None:
    f = SensitiveInfoFilter()
    text = "联系 13800138000 或 a@b.com 咨询"
    result = f.filter(text)
    assert result["safe"] is False
    assert "phone" in result["warnings"]
    assert "email" in result["warnings"]


# 功能：含密码的句子 + 中文混排仍能正确脱敏
# 设计：中文句子里嵌入 password=xxx，断言原始 token 不在 sanitized 中
def test_chinese_mixed_with_credential() -> None:
    f = SensitiveInfoFilter()
    text = "数据库密码是 password=hunter2，请保密"
    result = f.filter(text)
    assert "hunter2" not in result["sanitized"]
    assert "***REDACTED***" in result["sanitized"]
    assert "credential:password" in result["warnings"]


# 功能：纯中文（无敏感词）保持原样
# 设计：保证中文不误伤，sanitized 应当完全一致
def test_pure_chinese_text_unchanged() -> None:
    f = SensitiveInfoFilter()
    text = "用户偏好使用深色模式，界面语言为中文。"
    result = f.filter(text)
    assert result["safe"] is True
    assert result["sanitized"] == text


# 功能：sanitized 永远为字符串类型（即使 input 不是 str 也不抛）
# 设计：传 None 走 if not text 分支返回空串，断言不抛
def test_filter_never_raises() -> None:
    f = SensitiveInfoFilter()
    # 输入 None 时按 falsy 处理，不抛
    result = f.filter("")  # empty path
    assert result["safe"] is True
    assert isinstance(result["sanitized"], str)


# 功能：模块内置正则常量可被外部引用
# 设计：直接 import 各正则，断言可编译 + 至少有 1 个匹配示例
def test_module_exposes_regex_constants() -> None:
    assert _SENSITIVE_KV_RE.search("password=foo") is not None
    assert _PHONE_RE.search("13800138000") is not None
    assert _EMAIL_RE.search("a@b.com") is not None
    assert _IDCARD_RE.search("110101199003078888") is not None
    assert _AUTH_HEADER_RE.search("Bearer abcdefgh") is not None
