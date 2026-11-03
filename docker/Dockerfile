FROM python:3.11-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
# The wheel build compiles frontend assets and all translation catalogs.
RUN python -m pip install --upgrade pip \
    && python -m pip wheel . -w /wheels --no-deps

FROM python:3.11-slim AS runtime
ARG WIRECLOUD_INSTALL_MCP=false

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/docker

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY constraints-mcp.txt /app/constraints-mcp.txt
RUN if [ "$WIRECLOUD_INSTALL_MCP" = "true" ]; then \
        python -m pip install --no-cache-dir -c /app/constraints-mcp.txt /wheels/wirecloud-*.whl 'mcp==2.3.0'; \
    else \
        python -m pip install --no-cache-dir /wheels/wirecloud-*.whl; \
    fi \
    && rm -rf /wheels

COPY docker/settings.py /app/docker/settings.py
COPY docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["uvicorn", "wirecloud.main:app", "--host", "0.0.0.0", "--port", "8000"]
