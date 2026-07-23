"""测试 .env.example 完整性与安全性（Wave 7 WT-K1）。

设计：
- 10+ 个测试覆盖 .env.example 的 13 段必含 key
- 必查：不含真 key 模式（sk- 32+ 字符 / Bearer sk-）
- 必查：所有占位符（无真值）
- 必查：覆盖计划 §三 WT-K1 列出的所有 13 段
- 不依赖 docker / network：纯文件解析，单测 0.1s 内完成
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# 仓库根 = tests/unit/test_env_example.py 的 ../../
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"


# 功能：定位 .env.example
# 设计：先验证文件存在（fail-loud，便于 CI 报错定位）
def test_env_example_exists() -> None:
    assert ENV_EXAMPLE.exists(), f".env.example 必须存在: {ENV_EXAMPLE}"


# 功能：缓存 .env.example 内容供所有用例复用
# 设计：避免每个测试都重新 IO 读盘
@pytest.fixture(scope="module")
def env_content() -> str:
    return ENV_EXAMPLE.read_text(encoding="utf-8")


# 功能：解析 .env.example 全部 KEY
# 设计：用正则提取每行 `KEY=...` 或 `# KEY=...`（注释行也算），
#       去掉 `${VAR:-default}` / `~` 等展开形式，保留 KEY 本身
@pytest.fixture(scope="module")
def env_keys(env_content: str) -> set[str]:
    keys: set[str] = set()
    for line in env_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # 取 = 前的 key
        if "=" in line:
            k = line.split("=", 1)[0].strip()
            if k and re.match(r"^[A-Z_][A-Z0-9_]*$", k):
                keys.add(k)
    return keys


# 功能：扫描 .env.example 不含真 API key 模式
# 设计：占位符 `sk-ant-...` 长度 < 20 不命中；真 key 至少 32+ 字符
#       模式：sk- 后续 32+ 字符 / Bearer sk-* / sk-ant- 后续 20+
@pytest.mark.parametrize(
    "pattern",
    [
        r"sk-[a-zA-Z0-9]{32,}",          # 通用 sk- 真 key
        r"Bearer sk-[a-zA-Z0-9]{20,}",    # Bearer 真 key
        r"sk-ant-[a-zA-Z0-9]{20,}",       # Anthropic 真 key
        r"sk-[a-zA-Z0-9]{40}",            # OpenAI 真 key
    ],
)
def test_env_example_no_real_key(env_content: str, pattern: str) -> None:
    """占位符 `sk-ant-...` 因长度 < 20 不应命中；真 key 必须 32+ 字符。"""
    matches = re.findall(pattern, env_content)
    assert matches == [], f".env.example 含疑似真 API key ({pattern}): {matches[:3]}"


# 功能：占位符格式必须以 `sk-ant-...` 或 `sk-...` 结尾
# 设计：示例值用 `...` 收尾，便于人眼识别
def test_env_example_uses_placeholder_syntax(env_content: str) -> None:
    # 找所有 sk- 出现的位置
    sk_lines = [
        line.strip() for line in env_content.splitlines() if "sk-" in line and not line.strip().startswith("# 功能") and not line.strip().startswith("# 设计")
    ]
    # 至少有一行是占位符（我们的 .env.example 至少 1 个 ANTHROPIC_API_KEY 注释行）
    assert any("sk-ant-..." in line or "sk-..." in line for line in sk_lines), (
        "应至少 1 行占位符（sk-ant-... 或 sk-...）作为示例"
    )


# 功能：13 段必须全部覆盖（与计划 §三 WT-K1 + .env.example 注释对齐）
# 设计：每段至少 1 个 KEY 出现在 .env.example
@pytest.mark.parametrize(
    "segment,required_keys",
    [
        ("[Core]",       ["KAMA_HOST", "KAMA_PORT"]),
        ("[Logging]",    ["KAMA_LOG_LEVEL", "KAMA_LOG_FILE", "KAMA_LOG_FORMAT"]),
        ("[Config]",     []),  # 可选段，允许 0 key
        ("[LLM]",        ["KAMA_LLM_DEFAULT_MODEL", "KAMA_LLM_PROVIDER", "KAMA_MAX_STEPS"]),
        ("[Embedding]",  ["KIVI_EMBEDDING_PROVIDER", "KIVI_EMBEDDING_DIMS", "KIVI_EMBEDDING_MODEL"]),
        ("[Gateway]",    ["KIVI_GATEWAY_HOST", "KIVI_GATEWAY_PORT", "KIVI_GATEWAY_CORS_ORIGINS"]),
        ("[Memory]",     ["KIVI_MEMORY_BACKEND", "KIVI_AUTO_FALLBACK"]),
        ("[OpenAI]",     []),  # OPENAI_API_KEY 注释即可，KEY 在 [LLM] 段
        ("[Elasticsearch]", ["KIVI_ES_URL", "KIVI_ES_VERIFY_CERTS", "KIVI_ES_REQUEST_TIMEOUT_S"]),
        ("[Redis]",      ["KIVI_REDIS_URL", "KIVI_EVAL_BACKEND", "KIVI_EVAL_STREAM", "KIVI_EVAL_SAMPLE_RATE"]),
        ("[Postgres]",   ["KIVI_DB_MODE", "KIVI_DATABASE_URL"]),
        ("[RAG]",        ["KIVI_RAG_MODE", "KIVI_RAG_TIMEOUT_S"]),
        ("[Health]",     ["KIVI_HEALTH_INTERVAL_S", "KIVI_HEALTH_TIMEOUT_S"]),
        ("[Chatbox Frontend]", ["VITE_API_PROXY_TARGET", "VITE_WS_PROXY_TARGET", "VITE_DEV_PORT"]),
    ],
)
def test_env_example_covers_all_segments(
    env_keys: set[str], segment: str, required_keys: list[str]
) -> None:
    """每个 [段] 必须含预期 KEY 子集。"""
    missing = [k for k in required_keys if k not in env_keys]
    assert not missing, f"{segment} 段缺失 key: {missing}"


# 功能：.env.example 头部必须有使用说明（cp / 不要提交 / 段说明）
# 设计：文档完整性，避免新人照搬错误
def test_env_example_has_usage_header(env_content: str) -> None:
    assert "cp .env.example .env" in env_content, "应有 cp .env.example .env 用法说明"
    assert "不要提交" in env_content or "never commit" in env_content.lower(), (
        "应明确说明 .env 不能提交"
    )


# 功能：.env.example 必含 13 段注释标记
# 设计：每段头有 [段名] 注释，便于 grep 定位
def test_env_example_has_all_segment_headers(env_content: str) -> None:
    expected_segments = [
        "[Core]", "[Logging]", "[Config]", "[LLM]", "[Embedding]",
        "[Gateway]", "[Memory]", "[OpenAI]", "[Elasticsearch]", "[Redis]",
        "[Postgres]", "[RAG]", "[Health]", "[Chatbox Frontend]",
    ]
    for seg in expected_segments:
        assert seg in env_content, f"缺少段标记: {seg}"


# 功能：.env.example 不应直接含真 password
# 设计：常见弱密码不应出现在示例（即便以注释形式）
@pytest.mark.parametrize(
    "weak_password",
    ["password=123456", "PASSWORD=admin", "PASSWORD=root"],
)
def test_env_example_no_weak_passwords(env_content: str, weak_password: str) -> None:
    assert weak_password.lower() not in env_content.lower(), (
        f"含弱密码示例: {weak_password}"
    )


# 功能：占位符 .env.example 不应含内网 IP
# 设计：示例值应是 127.0.0.1 / 0.0.0.0 / 占位符；不应含 10.x / 192.168.x / 172.16-31.x
def test_env_example_no_internal_ip_leak(env_content: str) -> None:
    # 匹配 `192.168.` / `10.0.` / `172.16.` / `172.17.` ... 等内网网段
    internal_patterns = [
        r"\b192\.168\.\d{1,3}\.\d{1,3}\b",
        r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
        r"\b172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}\b",
    ]
    for pat in internal_patterns:
        matches = re.findall(pat, env_content)
        assert matches == [], f".env.example 不应含内网 IP ({pat}): {matches[:3]}"


# 功能：所有出现的 KIVI_/KAMA_ 变量名都应是合法的 env var 名
# 设计：fail-loud；后续扩展 KEY 时格式一致性
def test_env_example_key_names_are_valid(env_keys: set[str]) -> None:
    invalid = [k for k in env_keys if not re.match(r"^[A-Z][A-Z0-9_]*$", k)]
    assert not invalid, f"非法 KEY 名（应全大写 + 下划线）: {invalid}"


# 功能：段标记后应有功能说明（不只一个 [段名] 标签）
# 设计：防止空段（plan 验收要求每段有内容）
# 注：[Config] / [OpenAI] / [Database] 是引用段（KEY 在 [LLM] / [Postgres] 段），允许空
OPTIONAL_SEGMENTS = frozenset({"[Config]", "[OpenAI]", "[Database]"})
def test_env_example_segments_have_content(env_content: str) -> None:
    # 把内容按段切片（[段名] 开头）
    chunks = re.split(r"(?m)^# ── \[[A-Z][A-Za-z ]+\]", env_content)
    # chunks[0] 是文件头；后面每个 chunk 是一个段
    assert len(chunks) >= 14, f"应有 14+ 段（13 段 + 文件头），实际 {len(chunks) - 1} 段"
    # 提取段名（用于判定 optional）
    seg_names = re.findall(r"(?m)^# ── (\[[A-Z][A-Za-z ]+\])", env_content)
    # 每段至少 1 行非空非纯注释（实际有 KEY=... 行），[Config] 段是可选
    for i, (seg_name, chunk) in enumerate(zip(seg_names, chunks[1:]), 1):
        if seg_name in OPTIONAL_SEGMENTS:
            continue
        has_key = any(
            re.match(r"^[A-Z_][A-Z0-9_]*=", line.strip())
            for line in chunk.splitlines()
        )
        assert has_key, f"段 {i} ({seg_name}) 缺少 KEY= 行"


# 功能：.env.example 与 docker-compose.yml 端口引用一致
# 设计：.env 里的 KAMA_PORT=7437 / KIVI_GATEWAY_PORT=8000 必须与 docker-compose ports 匹配
def test_env_example_ports_match_compose() -> None:
    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    # .env KAMA_PORT
    env_text = ENV_EXAMPLE.read_text(encoding="utf-8")
    m = re.search(r"^KAMA_PORT=(\d+)$", env_text, re.MULTILINE)
    assert m, "KAMA_PORT 必须定义"
    assert m.group(1) in compose_text, f"KAMA_PORT={m.group(1)} 未在 docker-compose 中使用"
    # .env KIVI_GATEWAY_PORT
    m = re.search(r"^KIVI_GATEWAY_PORT=(\d+)$", env_text, re.MULTILINE)
    assert m, "KIVI_GATEWAY_PORT 必须定义"
    assert m.group(1) in compose_text, f"KIVI_GATEWAY_PORT={m.group(1)} 未在 docker-compose 中使用"


# 功能：覆盖 [OpenAI] 段占位符格式
# 设计：注释中应有 OPENAI_API_KEY=sk-... 占位符
def test_env_example_openai_placeholder(env_content: str) -> None:
    # 注释行可包含占位符
    assert "OPENAI_API_KEY" in env_content, "应提到 OPENAI_API_KEY"
    # 应至少有占位符 `sk-...`
    assert "sk-..." in env_content, "应包含 sk-... 占位符"
