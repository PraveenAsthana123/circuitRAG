# documind_core — shared Python foundation

Every Python service in DocuMind depends on this package. It is **intentionally thin**: exceptions, config, logging, middleware, the primitives every service needs — and nothing else.

## Install (editable, from a service)

```bash
# From the repo root:
pip install -e ./libs/py
```

Each service's `requirements.txt` pulls it in via a relative path:

```
-e ../../libs/py
```

## Module map

| Module               | What it provides                                        | Design area(s)     |
|----------------------|---------------------------------------------------------|--------------------|
| `config`             | Pydantic Settings — single source of truth for env     | 6, 55, 65          |
| `exceptions`         | Domain-error hierarchy (AppError → Not/Val/Data/…)      | 9, cross-cutting   |
| `logging_config`     | structlog JSON logs + correlation/tenant/user ctx       | 62                 |
| `middleware`         | FastAPI middleware stack (CID, security, tenant, RL)    | 5, 62              |
| `circuit_breaker`    | CLOSED/HALF_OPEN/OPEN state machine                     | 4, Extra (CB)      |
| `rate_limiter`       | Redis sliding-window limiter                            | 42, 45             |
| `db_client`          | asyncpg pool + tenant-scoped connections (RLS)          | 5, 46              |
| `cache`              | Redis cache-aside with tenant keys + stampede lock      | 40, 41, 42         |
| `kafka_client`       | CloudEvents producer + idempotent consumer              | 17, 19, 20, 31, 44 |
| `observability`      | OpenTelemetry + Prometheus setup                        | 62, 64             |
| `encryption`         | Fernet at-rest secret encryption                        | 3                  |
| `idempotency`        | `X-Idempotency-Key` Redis cache                         | 20                 |
| `schemas`            | SuccessResponse, PaginatedResponse, ErrorResponse, Health| §6 of global CLAUDE |

## Principles

1. **No FastAPI imports at import-time.** `middleware.py` imports Starlette types; that's as high as the dependency ladder goes. The lib is usable from CLI tools, Kafka consumers, eval workers, migration scripts.
2. **Constructor injection everywhere.** No module-level `client = Redis(...)`. Every class takes its dependencies in `__init__` — tests can pass fakes.
3. **No globals.** Settings are cached via `get_settings()`; logging uses ContextVars. No `_cache = {}` at module level.
4. **Observability is automatic.** Any service that calls `setup_logging` + `setup_observability` + `instrument_fastapi` gets JSON logs, OTel traces, and Prometheus metrics for free.

## Typical service wiring

```python
# services/<svc>/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from documind_core.config import get_settings
from documind_core.logging_config import setup_logging
from documind_core.observability import setup_observability, instrument_fastapi, instrument_asyncpg
from documind_core.middleware import (
    CorrelationIdMiddleware, SecurityHeadersMiddleware,
    TenantContextMiddleware, RateLimitMiddleware,
    register_exception_handlers,
)
from documind_core.db_client import DbClient
from documind_core.cache import Cache
from documind_core.rate_limiter import RateLimiter
import redis.asyncio as aioredis

from app.core.config import ServiceSettings  # your subclass

settings = get_settings(ServiceSettings)

setup_logging(service_name=settings.service_name, level=settings.log_level, json_format=settings.log_json)
setup_observability(
    service_name=settings.service_name,
    otlp_endpoint=settings.otel_exporter_otlp_endpoint,
    prometheus_port=settings.prometheus_port,
    environment=settings.env,
)

db = DbClient(dsn=settings.postgres_dsn, min_size=settings.pg_min_conns, max_size=settings.pg_max_conns)
redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
cache = Cache(redis_client)
limiter = RateLimiter(redis_client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    instrument_asyncpg()
    yield
    await db.close()


app = FastAPI(title=settings.service_name, lifespan=lifespan)
app.add_middleware(RateLimitMiddleware, limiter=limiter,
                   default_limit_per_min=settings.rate_limit_api_per_min)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CorrelationIdMiddleware)
register_exception_handlers(app)
instrument_fastapi(app)
```

Middleware is added in REVERSE order — Starlette wraps from the inside out. Put CorrelationIdMiddleware LAST in code so it runs FIRST at runtime.
