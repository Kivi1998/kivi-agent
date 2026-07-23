# =====================================================================
# kivi-gateway (FastAPI) 镜像（Wave 7 WT-K1）
# =====================================================================
# 功能：把 kivi-agent + FastAPI/uvicorn 打包，监听 8000
# 设计：复用 builder 阶段（同 core 镜像），runtime 阶段用 uvicorn 启动
# 入口：uvicorn kivi_agent.gateway.main:create_app --factory --host 0.0.0.0 --port 8000
# =====================================================================

# ---- Stage 1: builder（与 core.Dockerfile 一致；可用 multi-target 共享） ----
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY README.md ./

RUN uv sync --frozen --no-install-project 2>/dev/null || uv sync --no-install-project
RUN uv sync --frozen 2>/dev/null || uv sync

# ---- Stage 2: runtime ----
FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=builder /app /app

# curl 用于 healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash kivi
WORKDIR /app
RUN chown -R kivi:kivi /app

USER kivi

# 用 uvicorn 跑 FastAPI；--factory 因为 create_app 是工厂函数
ENTRYPOINT ["uvicorn", "kivi_agent.gateway.main:create_app", \
            "--factory", "--host", "0.0.0.0", "--port", "8000"]

EXPOSE 8000
