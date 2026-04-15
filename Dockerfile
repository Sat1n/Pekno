ARG NODE_IMAGE=node:20-bookworm-slim
ARG BASE_IMAGE=python:3.13-slim

FROM ${NODE_IMAGE} AS web-builder
WORKDIR /app/web

COPY web/package.json ./
RUN npm install

COPY web ./
RUN npm run build


FROM ${BASE_IMAGE} AS app-runtime
ARG EXECUTION_MODE=cpu

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    EXECUTION_MODE=${EXECUTION_MODE}

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && if ! command -v python >/dev/null 2>&1; then apt-get install -y --no-install-recommends python3 python3-pip python3-venv; fi \
    && if ! command -v python >/dev/null 2>&1; then ln -sf /usr/bin/python3 /usr/local/bin/python; fi \
    && if ! command -v pip >/dev/null 2>&1; then ln -sf /usr/bin/pip3 /usr/local/bin/pip; fi \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir uv

COPY pyproject.toml ./pyproject.toml
COPY uv.lock ./uv.lock
RUN uv sync --frozen --no-dev

COPY . .
COPY --from=web-builder /app/web/dist /app/web/dist

RUN chmod +x /app/docker-entrypoint.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uv", "run", "python", "hub/main.py"]


FROM nginx:stable-alpine AS nginx-runtime
COPY docker/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=web-builder /app/web/dist /usr/share/nginx/html
