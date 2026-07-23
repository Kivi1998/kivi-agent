# =====================================================================
# chatbox-frontend (Vue 3 + Vite) 镜像（Wave 7 WT-K1）
# =====================================================================
# 功能：把 apps/web-chat 打包成开发服务器镜像
# 设计：
#   - 多阶段：builder 装 deps + 构建；runtime 用 vite dev 服务器
#   - 当前 WT-K1 阶段用 dev 模式（vite dev）；生产可改为 preview + nginx（K4 文档化）
#   - 镜像路径在 apps/web-chat/，构建时需 docker build -f docker/chatbox.Dockerfile apps/web-chat
# =====================================================================

# ---- Stage 1: builder（装 npm 依赖） ----
FROM node:20-alpine AS builder

WORKDIR /app

# 装 deps
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY . .

# ---- Stage 2: runtime（Vite dev server） ----
FROM node:20-alpine AS runtime

# 健康检查需要的工具（Alpine 自带 wget）
RUN apk add --no-cache wget

WORKDIR /app

# 拷 node_modules + 源码（dev 模式无需 build）
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app ./

# Vite dev server 配置已在 vite.config.ts 中：port=5173 + 代理 /api / /sessions
EXPOSE 5173

# dev 模式：监听 0.0.0.0 让容器外可访问
ENV HOST=0.0.0.0

# 注意：build 阶段用过 vue-tsc，需要保留 tsconfig
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
