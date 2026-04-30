#!/usr/bin/env python3
# RESOURCES: readonly
"""
Drill: sidecar rating surface wiring.

Verifies the `/admin/sidecar` write surface exists without requiring a
running Next.js app.

Negative assertions cover: page exists with rating UI affordances,
API route exists at the canonical path, and the page calls the
route with the expected fields. Without these, the rating surface
is a dead button — no observability of operator decisions.
"""
from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
PAGE = REPO / "services" / "frontend" / "app" / "admin" / "sidecar" / "page.tsx"
ROUTE = (
    REPO
    / "services"
    / "frontend"
    / "app"
    / "api"
    / "v1"
    / "sidecar"
    / "events"
    / "[eventId]"
    / "rating"
    / "route.ts"
)
LIB = REPO / "services" / "frontend" / "lib" / "sidecar.ts"
DETAIL = REPO / "services" / "frontend" / "app" / "admin" / "sidecar" / "[eventId]" / "page.tsx"


def fail(msg: str) -> None:
    print(f"x {msg}")
    raise SystemExit(1)


def ok(msg: str) -> None:
    print(f"ok {msg}")


def main() -> None:
    if not PAGE.exists():
        fail(f"missing sidecar page: {PAGE}")
    if not ROUTE.exists():
        fail(f"missing rating route: {ROUTE}")
    if not LIB.exists():
        fail(f"missing sidecar helper lib: {LIB}")
    if not DETAIL.exists():
        fail(f"missing sidecar event detail page: {DETAIL}")

    page_text = PAGE.read_text(encoding="utf-8")
    route_text = ROUTE.read_text(encoding="utf-8")
    lib_text = LIB.read_text(encoding="utf-8")

    for needle in (
        "Live event ratings",
        "/api/v1/sidecar/events/${event.id}/rating",
        'name="rating" value="useful"',
        'name="rating" value="not_useful"',
        'name="event_type"',
        'name="rating_state"',
        'name="q"',
        "Apply filters",
        "Reset",
        "Matched events",
        "Top reviewers",
        "Previous page",
        "Next page",
    ):
        if needle not in page_text:
            fail(f"sidecar page missing {needle!r}")
    ok("sidecar page exposes live rating forms + filter controls")

    for needle in (
        "export async function GET",
        "export async function POST",
        "rateSidecarEvent",
        "rated_by",
        "rating_notes",
        "rating",
        "saved",
        "missing",
        "invalid",
        "failed",
    ):
        if needle not in route_text:
            fail(f"rating route missing {needle!r}")
    ok("rating route exposes POST contract and redirect states")

    for needle in (
        "listRecentSidecarEvents",
        "listSidecarEventPage",
        "ratingState",
        "eventType",
        "search",
        "offset",
        "reviewers",
        "total",
        "rateSidecarEvent",
        "getSidecarEventById",
        "advisor.record_rating",
        "advisor.db",
        "rated_by",
        "rating_notes",
    ):
        if needle not in lib_text:
            fail(f"sidecar helper missing {needle!r}")
    ok("helper bridges sidecar read/write to advisor.db")

    detail_text = DETAIL.read_text(encoding="utf-8")
    for needle in (
        "Sidecar event #",
        "Captured content",
        "Advisor output",
        "getSidecarEventById",
        "Operator review",
        "rated_by",
        "rating_notes",
        'href="/admin/sidecar"',
    ):
        if needle not in detail_text:
            fail(f"sidecar detail page missing {needle!r}")
    ok("sidecar detail page exposes event drill-down")

    print("ALL 4 SIDECAR-RATING-SURFACE STEPS PASSED")


if __name__ == "__main__":
    main()
