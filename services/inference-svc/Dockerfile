# syntax=docker/dockerfile:1.7
FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

FROM base AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY libs/py /app/libs/py
COPY services/inference-svc/requirements.txt /app/services/inference-svc/
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && pip install -e /app/libs/py && pip install -r /app/services/inference-svc/requirements.txt

FROM base AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 documind && useradd -u 10001 -g documind -m documind
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/libs/py /app/libs/py
COPY --chown=documind:documind services/inference-svc /app/services/inference-svc
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH="/app/services/inference-svc:/app/libs/py"
USER documind
WORKDIR /app/services/inference-svc
EXPOSE 8084
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
    CMD curl -fsS "http://localhost:${INFERENCE_HTTP_PORT:-8084}/health" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8084"]
