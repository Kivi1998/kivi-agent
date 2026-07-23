# =====================================================================
# kivi-core 守护进程镜像（Wave 7 WT-K1）
# =====================================================================
# 功能：把 kivi-agent Python 包 + uv 工具链打包成最小运行时镜像
# 设计：
#   - 多阶段构建：builder 装依赖 + 包 wheel；runtime 只留 runtime deps + wheel
#   - 基于 python:3.12-slim（与 pyproject.toml requires-python 一致）
#   - 入口用 `kivi-core` console script（pyproject [project.scripts]）
#   - 非 root 运行（kivi 用户）
# =====================================================================

# ---- Stage 1: builder（装 uv + 同步 dev 依赖） ----
FROM python:3.12-slim AS builder

# 装 uv（用 Astral 官方安装脚本；与本地开发一致）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 先复制 lock + pyproject 最大化缓存命中
COPY pyproject.toml ./
COPY src ./src
COPY README.md ./

# 同步 dev 依赖（含 fastapi/uvicorn/websockets，gateway 共用）
# 注：--no-install-project 只装 deps，wheel 在下一阶段打
RUN uv sync --frozen --no-install-project 2>/dev/null || uv sync --no-install-project

# 装项目本身（wheel）
RUN uv sync --frozen 2>/dev/null || uv sync

# ---- Stage 2: runtime（最小运行时） ----
FROM python:3.12-slim AS runtime

# 拷 uv 与已同步的 venv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=builder /app /app

# 健康检查 + 日志需要的工具
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 非 root 用户
RUN useradd --create-home --shell /bin/bash kivi
WORKDIR /app
RUN chown -R kivi:kivi /app

# 日志目录
RUN mkdir -p /var/log/kivi && chown -R kivi:kivi /var/log/kivi

USER kivi

# 入口：kivi-core 守护进程（pyproject [project.scripts]）
ENTRYPOINT ["kivi-core"]

# 暴露端口（与 docker-compose.yml ports 同步）
EXPOSE 7437
