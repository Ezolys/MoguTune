# ---- クライアント (React) のビルド ----
FROM node:22-alpine AS client-build

WORKDIR /client
COPY dashboard/client/package.json dashboard/client/package-lock.json ./
RUN npm ci
COPY dashboard/client/ ./
RUN npm run build

# ---- サーバー (FastAPI) ----
FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
	UV_LINK_MODE=copy \
	UV_COMPILE_BYTECODE=1

WORKDIR /app

RUN pip install --no-cache-dir uv

# 依存関係のみ先にインストールしてレイヤーをキャッシュする
COPY dashboard/server/pyproject.toml dashboard/server/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY dashboard/server/src /app/src
RUN uv sync --frozen --no-dev

# ビルド済みクライアントを FastAPI が静的配信する
COPY --from=client-build /client/dist /app/static

ENV PATH="/app/.venv/bin:$PATH" \
	DASHBOARD_STATIC_DIR=/app/static

EXPOSE 8787
CMD ["uvicorn", "mogutune_dashboard.main:app", "--host", "0.0.0.0", "--port", "8787"]
