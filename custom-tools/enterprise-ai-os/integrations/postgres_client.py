# ✅ P0 IMPROVED (Iter 33, 2026-05-17): connection pool via
#     psycopg2.pool.ThreadedConnectionPool. Pre-fix the client held
#     a SINGLE connection — meaning concurrent FastAPI requests
#     serialized on it (and any blocking query stalled every other
#     request).
#
#     Now:
#       - Pool size configurable via env (POSTGRES_POOL_MIN/MAX,
#         defaults 1/10).
#       - query() acquires a connection from the pool, runs the
#         query inside an explicit transaction (with rollback on
#         exception), and releases the connection back.
#       - close() drains the entire pool.
#       - Pool is thread-safe (ThreadedConnectionPool).
#
#     For async FastAPI workloads, the right answer is psycopg3 or
#     asyncpg with an async pool. This stub keeps psycopg2 for
#     compat with the pre-fix interface; the sync-pool change still
#     unlocks parallelism per-worker.

import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor


_DEFAULT_MIN = 1
_DEFAULT_MAX = 10


class PostgresClient:
    def __init__(
        self,
        min_connections: int | None = None,
        max_connections: int | None = None,
    ):
        min_c = min_connections if min_connections is not None else \
            int(os.getenv("POSTGRES_POOL_MIN", str(_DEFAULT_MIN)))
        max_c = max_connections if max_connections is not None else \
            int(os.getenv("POSTGRES_POOL_MAX", str(_DEFAULT_MAX)))
        if min_c < 1 or max_c < min_c:
            raise ValueError("invalid pool bounds")

        self._pool = pool.ThreadedConnectionPool(
            minconn=min_c,
            maxconn=max_c,
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=os.getenv("POSTGRES_PORT", "5432"),
            dbname=os.getenv("POSTGRES_DB", "aios"),
            user=os.getenv("POSTGRES_USER", "aiuser"),
            password=os.getenv("POSTGRES_PASSWORD", "aipassword"),
        )

    def query(self, sql: str, params: tuple = ()):
        conn = self._pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                try:
                    cursor.execute(sql, params)
                except Exception:
                    conn.rollback()
                    raise
                conn.commit()
                if cursor.description:
                    return cursor.fetchall()
                return []
        finally:
            self._pool.putconn(conn)

    def close(self):
        """Drain the entire pool."""
        self._pool.closeall()
