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

from documind_core.db_client import Repository

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
            log.warning("prompt_repo_reload_failed using_cached_count=%d err=%s", len(self._cache), exc)
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

        # Stage-5 GEPA-active overlay (per ADR-024-style chain + commit
        # 67df048's promote_gepa_prompts gate). When
        # GEPA_PROMPT_LOADER_ENABLED=1 AND .loop/gepa_active_prompts.json
        # exists (only present when the Stage-4 promotion gate has
        # passed), overlay the optimized prompts as separate version
        # keys (e.g. "rag.qa_v1_gepa") so callers can A/B by version.
        # Baseline DB rows remain untouched — Stage-6 (deferred) wires
        # the canary traffic-split that picks gepa version for X%.
        # Per §47 fail-safe: any error reading the artifact → skip
        # overlay; baseline cache unchanged.
        gepa_count = self._overlay_gepa_active(new_cache)

        async with self._lock:
            self._cache = new_cache
        log.info(
            "prompt_cache_reloaded count=%d gepa_overlay=%d",
            len(new_cache), gepa_count,
        )

    def _overlay_gepa_active(self, cache: dict[str, PromptTemplate]) -> int:
        """Stage-5 GEPA overlay: read .loop/gepa_active_prompts.json and
        merge into cache as `name_gepa-{ts}` version keys.

        Returns the number of GEPA prompts overlaid. Default-deny:
        GEPA_PROMPT_LOADER_ENABLED=1 required to activate. Per §47
        fail-safe: any read/parse error → return 0, baseline cache
        intact.

        Composes with:
          scripts/promote_gepa_prompts.py — produces the artifact
          docs/architecture/empirical-rag-config-loop.md — chain
          §43 drill — drill_prompt_repo_gepa_overlay_stage5
          §47 fail-safe — error never breaks baseline reload
        """
        import os
        import json as _json
        from pathlib import Path

        if os.environ.get("GEPA_PROMPT_LOADER_ENABLED", "").strip() != "1":
            return 0

        # Path is fixed at the artifact's canonical location; operators
        # who relocate the .loop dir can override via env.
        path = os.environ.get(
            "GEPA_ACTIVE_PROMPTS_PATH",
            ".loop/gepa_active_prompts.json",
        )
        p = Path(path)
        if not p.exists():
            return 0
        try:
            data = _json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("gepa_overlay_parse_failed path=%s err=%s", path, exc)
            return 0

        promoted_at = data.get("promoted_at_ts", 0)
        version_tag = f"gepa-{int(promoted_at)}" if promoted_at else "gepa-active"
        optimized = data.get("optimized_prompts") or {}
        # Path-B alignment hint (per docs/architecture/
        # gepa-chain-status-and-stage6-blocker.md). When the gate's
        # artifact carries `gepa_target_prompt`, the overlay ALSO
        # registers the tuned prompt under that runtime name so a
        # rag_inference lookup of `<target>_gepa-<ts>` resolves
        # correctly. Without this hint, GEPA-tagged versions sit in
        # cache under predictor namespace (e.g. predict.predict_gepa-...)
        # which doesn't match the runtime self._default_prompt lookup.
        gepa_target = (data.get("gepa_target_prompt") or "").strip() or None

        count = 0
        for predictor_name, payload in optimized.items():
            instructions = (payload.get("instructions") or "").strip()
            if not instructions:
                # Defensive: gate should have rejected, but double-check
                continue
            # GEPA's predictor names are like "predict.predict" — map to
            # a stable cache key. We register under "<predictor>_<version>"
            # so callers asking for the gepa-tuned version pick it
            # explicitly. Stage-6 (deferred) does the traffic-split.
            tmpl = PromptTemplate(
                name=predictor_name,
                version=version_tag,
                system=instructions,
                user_template="{query}",  # GEPA tunes the system message
                max_context_tokens=4000,
            )
            primary_key = f"{predictor_name}_{version_tag}"
            cache[primary_key] = tmpl
            count += 1
            # Path-B alias: ALSO register under the operator-declared
            # runtime target name so canary lookup resolves. Only fires
            # for the FIRST predictor (typical: predict.predict in a
            # single-stage CouncilProgram); multi-predictor GEPA outputs
            # need Path A's per-predictor mapping which is out of scope.
            if gepa_target and not any(
                k.startswith(f"{gepa_target}_gepa-")
                for k in cache.keys()
            ):
                alias_key = f"{gepa_target}_{version_tag}"
                cache[alias_key] = PromptTemplate(
                    name=gepa_target,
                    version=version_tag,
                    system=instructions,
                    user_template="{query}",
                    max_context_tokens=4000,
                )
        return count

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
