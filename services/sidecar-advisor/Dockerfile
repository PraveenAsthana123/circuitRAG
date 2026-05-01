# syntax=docker/dockerfile:1.7
#
# §19 Dockerfile for sidecar-advisor.
#
# sidecar-advisor is a Python library used by:
#   scripts/issue_dispatcher.py     (local-model lint dispatcher per §50)
#   scripts/capture_and_review.py   (post-commit advisor capture)
#   pre-commit hook (.pre-commit-config.yaml advisory drill review)
#
# It's not a deployable network service today — there's no main.py
# nor an HTTP listener. This image exists so:
#   1. §19 audit ("every service has a Dockerfile") passes.
#   2. CI can `docker build` the image to verify the package's
#      installation contract still holds when the source changes.
#   3. A future iteration can mount it as a sidecar worker (hence
#      the directory name) by adding an entrypoint script.
#
# Usage today:
#     docker build -f services/sidecar-advisor/Dockerfile -t sidecar-advisor:dev .
#     docker run --rm sidecar-advisor:dev python -c "import sidecar_advisor.advisor; print('ok')"

FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

FROM base AS builder
WORKDIR /build
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY libs/py /app/libs/py
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip \
    && pip install -e /app/libs/py \
    && pip install httpx pyyaml

FROM base AS runtime
# Non-root user per CLAUDE.md §13.13.
RUN groupadd -g 10001 documind \
    && useradd -u 10001 -g documind -m documind
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/libs/py /app/libs/py
# The directory is hyphenated by repo convention; the codebase loads
# it via importlib (see drill_sidecar_pr_review_council.py for the
# pattern). The smoke check below uses the same approach.
COPY --chown=documind:documind services/sidecar-advisor /app/services/sidecar-advisor
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/libs/py"
USER documind
WORKDIR /app/services/sidecar-advisor

# Healthcheck: load the advisor module via importlib (matching the
# repo's import pattern). Proves the install contract is intact
# without requiring an HTTP listener.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import importlib.util; spec = importlib.util.spec_from_file_location('advisor', '/app/services/sidecar-advisor/advisor.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); assert hasattr(m, 'Advisor')" || exit 1

# Default: smoke-test the package then exit. CI and operators can
# override with `python <module>.py`.
CMD ["python", "-c", "import importlib.util; spec = importlib.util.spec_from_file_location('advisor', '/app/services/sidecar-advisor/advisor.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('sidecar-advisor: Advisor class ready')"]
