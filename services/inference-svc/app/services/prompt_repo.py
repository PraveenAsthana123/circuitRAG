"""
DB-backed prompt registry (Design Area 32 — Prompt Contract).

Reads active prompt templates from ``governance.prompts``. Falls back to
the in-code `PROMPT_TEMPLATES` dict if the DB is unreachable — so a
misconfigured environment still has working defaults.

Rules:
* Only rows with `status='active'` are returned.
* Multiple versions can be active simultaneously (A/B); callers pick by
  name AND (optionally) version. If version is None, the highest version
  string wins.
* Polled every 30s; governance changes propagate within that window.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from documind_core.db_client import DbClient, Repository

from .prompt_builder import PROMPT_TEMPLATES, PromptTemplate

log = logging.getLogger(__name__)


class PromptRepo(Repository):
    """Governance schema read-side for prompt templates."""

    async def list_active(self) -> list[dict[str, Any]]:
        async with self._db.admin_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT name, version, template, variables, model,
                       temperature, max_tokens, status
                FROM governance.prompts
                WHERE status = 'active'
                ORDER BY name, version DESC
                """,
            )
        return [dict(r) for r in rows]


class DbBackedPromptBuilder:
    """
    Drop-in replacement for the in-memory `PromptBuilder`.

    Keeps the same `get(name)` + `build(...)` surface so callers don't
    change. Internally polls `PromptRepo.list_active` every `refresh_s`
    seconds and caches. On DB failure, returns the last good snapshot
    (and on cold start, falls back to `PROMPT_TEMPLATES`).

    The prompt template schema in the DB has ``system`` and ``user_template``
    columns merged into a single ``template`` column for storage
    simplicity — we split them with a sentinel separator
    ``---USER---`` so one row is one template.
    """

    SEP = "\n---USER---\n"

    def __init__(
        self,
        *,
        repo: PromptRepo | None = None,
        refresh_s: int = 30,
    ) -> None:
        self._repo = repo
        self._refresh_s = refresh_s
        # Start with the built-in dict — guaranteed to work even if the
        # governance DB is down during cold start.
        self._cache: dict[str, PromptTemplate] = dict(PROMPT_TEMPLATES)
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._repo is None:
            log.info("prompt_repo_absent using_builtin_templates=%d", len(self._cache))
            return
        # Initial load + background poller
        await self._reload()
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _poll_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._refresh_s)
                await self._reload()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("prompt_repo_poll_error")

    async def _reload(self) -> None:
        if self._repo is None:
            return
        try:
            rows = await self._repo.list_active()
        except Exception as exc:  # noqa: BLE001
            log.warning("prompt_repo_reload_failed using_cached_count=%d err=%s",
                        len(self._cache), exc)
            return

        new_cache: dict[str, PromptTemplate] = dict(PROMPT_TEMPLATES)
        for row in rows:
            key = f"{row['name']}_{row['version']}"
            template_text: str = row["template"]
            if self.SEP in template_text:
                system, user = template_text.split(self.SEP, 1)
            else:
                system, user = "", template_text
            new_cache[key] = PromptTemplate(
                name=row["name"],
                version=row["version"],
                system=system.strip(),
                user_template=user.strip(),
                max_context_tokens=int(row.get("max_tokens") or 4000),
            )
        async with self._lock:
            self._cache = new_cache
        log.info("prompt_cache_reloaded count=%d", len(new_cache))

    def get(self, name: str) -> PromptTemplate:
        try:
            return self._cache[name]
        except KeyError as exc:
            raise KeyError(f"Unknown prompt template '{name}'") from exc

    def build(
        self,
        *,
        template_name: str,
        query: str,
        chunks: list[dict[str, Any]],
    ) -> tuple[str, str, list[dict[str, Any]]]:
        # Delegate to the in-code builder so citation map logic stays
        # in one place. We just provide a different template lookup.
        from .prompt_builder import PromptBuilder
        return PromptBuilder({name: tmpl for name, tmpl in self._cache.items()}).build(
            template_name=template_name, query=query, chunks=chunks
        )
