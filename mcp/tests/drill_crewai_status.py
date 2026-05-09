#!/usr/bin/env python3
# RESOURCES: readonly
"""Drill: CrewAI remains non-primary unless ADR-027 is superseded.

NEGATIVE: CrewAI must not silently become a primary framework after rejection.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))


def main() -> int:
    print("-- 1. POSITIVE: CrewAI status script exports payload --")
    import crewai_status

    payload = crewai_status.status()
    crewai = payload["crewai"]
    print("  ok: payload shape stable")

    print("-- 2. NEGATIVE: CrewAI is not accepted as primary framework --")
    if crewai["accepted_primary_framework"] or crewai["ready_for_primary_use"]:
        print(f"x CrewAI unexpectedly marked primary-ready: {crewai}")
        return 1
    print("  ok: CrewAI not primary")

    print("-- 3. POSITIVE: ADR-027 is present and rejects CrewAI primary adoption --")
    if not crewai["adr_rejects_crewai"]:
        print(f"x ADR rejection evidence missing: {crewai}")
        return 1
    print("  ok: ADR-027 evidence present")

    print("-- 4. NEGATIVE: catalog row is not planned/shipped drift --")
    if crewai["catalog_status"] != "not_applicable":
        print(f"x CrewAI catalog status drifted: {crewai['catalog_status']}")
        return 1
    print("  ok: catalog records intentional non-adoption")

    print("\nALL 4 STEPS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
