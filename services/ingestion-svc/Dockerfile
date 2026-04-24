# syntax=docker/dockerfile:1.7
# Multi-stage build — small runtime image, layers ordered for cache hits.

FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ---- builder: install deps only ----
FROM base AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy the shared lib first so changes to a service's requirements.txt don't
# invalidate the shared-lib install layer.
COPY libs/py /app/libs/py
COPY services/ingestion-svc/requirements.txt /app/services/ingestion-svc/
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip \
    && pip install -e /app/libs/py \
    && pip install --no-deps --require-hashes -r /app/services/ingestion-svc/requirements.lock 2>/dev/null \
       || pip install -r /app/services/ingestion-svc/requirements.txt

# ---- runtime ----
FROM base AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmagic1 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 documind \
    && useradd -u 10001 -g documind -m -s /bin/bash documind

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/libs/py /app/libs/py
COPY --chown=documind:documind services/ingestion-svc /app/services/ingestion-svc

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/services/ingestion-svc:/app/libs/py"

USER documind
WORKDIR /app/services/ingestion-svc
EXPOSE 8082

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${INGESTION_HTTP_PORT:-8082}/health" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8082"]
