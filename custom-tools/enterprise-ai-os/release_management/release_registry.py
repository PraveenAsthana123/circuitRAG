# Added Iter 35 (2026-05-17) — in-memory release registry. Lets
# ReleaseEngine.rollback_release validate that target_release_id
# actually exists + is not itself a failed release before declaring
# the rollback "completed". Pre-fix you could roll back to a
# non-existent (or itself-failed) release and the engine would
# happily mark the rollback "completed" — pure theater.
#
# Real production needs a Postgres `releases` table backed by the
# CI/CD pipeline. This stub closes the validation gap.

from typing import Dict, Any, Optional


class ReleaseNotFoundError(Exception):
    pass


class ReleaseInvalidStateError(Exception):
    pass


class ReleaseRegistry:
    def __init__(self):
        self._releases: Dict[str, Dict[str, Any]] = {}

    def register(self, release: Dict[str, Any]) -> Dict[str, Any]:
        rid = release.get("release_id")
        if not rid:
            raise ValueError("release must have a release_id")
        self._releases[rid] = release
        return release

    def get(self, release_id: str) -> Dict[str, Any]:
        r = self._releases.get(release_id)
        if r is None:
            raise ReleaseNotFoundError(f"Release not found: {release_id}")
        return r

    def list_releases(self) -> list[Dict[str, Any]]:
        return list(self._releases.values())

    def update_status(self, release_id: str, status: str) -> Dict[str, Any]:
        r = self.get(release_id)
        r["status"] = status
        return r
