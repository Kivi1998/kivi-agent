from __future__ import annotations

from kama_claude.core.mcp.secrets import resolve_secret_refs


# 功能：验证形如 ${SECRET:NAME} 的值被替换成对应环境变量的实际值
# 设计：设置一个环境变量，构造引用它的 env 字典，断言解析后的值就是环境变量的真实值，
#      而不是字面量 "${SECRET:NAME}" 字符串
def test_resolve_secret_refs_substitutes_env_var(monkeypatch) -> None:
    monkeypatch.setenv("MY_API_KEY", "sk-real-secret-value")
    env = {"API_KEY": "${SECRET:MY_API_KEY}", "PLAIN": "not-a-secret"}
    resolved = resolve_secret_refs(env)
    assert resolved["API_KEY"] == "sk-real-secret-value"
    assert resolved["PLAIN"] == "not-a-secret"


# 功能：验证引用了未设置的环境变量时，解析结果为空字符串而不是抛异常
# 设计：连接失败应该交给 server 因为凭据为空而报错，而不是在这一层直接中断——
#      保持和现有 mcp start_all() "单个 server 失败只记日志跳过"的容错风格一致
def test_resolve_secret_refs_missing_env_var_becomes_empty(monkeypatch) -> None:
    monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
    env = {"API_KEY": "${SECRET:NONEXISTENT_KEY}"}
    resolved = resolve_secret_refs(env)
    assert resolved["API_KEY"] == ""
