#!/usr/bin/env python3
"""Lang observability status for LangSmith and Langfuse.

Offline-safe by design:
  - LangSmith status checks package + env readiness only; no SaaS calls.
  - Langfuse status checks local/self-hosted health when LANGFUSE_HOST or
    the default local port is configured.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from importlib.metadata import PackageNotFoundError, version
from typing import Any


def _version(pkg: str) -> str | None:
    try:
        return version(pkg)
    except PackageNotFoundError:
        return None


def _env_bool(*names: str) -> bool:
    for name in names:
        value = os.getenv(name, "").strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return True
    return False


def _http_health(url: str, timeout: float = 2.0) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            body = response.read(400).decode("utf-8", errors="replace")
            return {
                "url": url,
                "http_status": response.status,
                "healthy": 200 <= response.status < 300,
                "body_sample": body,
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        return {
            "url": url,
            "http_status": exc.code,
            "healthy": False,
            "body_sample": "",
            "error": str(exc),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "url": url,
            "http_status": 0,
            "healthy": False,
            "body_sample": "",
            "error": str(exc),
        }


def langsmith_status() -> dict[str, Any]:
    tracing_enabled = _env_bool("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2")
    api_key_present = bool(os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY"))
    endpoint = os.getenv("LANGSMITH_ENDPOINT") or os.getenv("LANGCHAIN_ENDPOINT") or "https://api.smith.langchain.com"
    return {
        "tool": "langsmith",
        "package_version": _version("langsmith"),
        "installed": _version("langsmith") is not None,
        "tracing_enabled_env": tracing_enabled,
        "api_key_present": api_key_present,
        "endpoint": endpoint,
        "offline_safe": True,
        "ready": tracing_enabled and api_key_present and _version("langsmith") is not None,
        "mode": "managed",
        "note": (
            "LangSmith is ready for managed tracing/eval"
            if tracing_enabled and api_key_present
            else "LangSmith installed but not enabled; set LANGSMITH_TRACING=true and LANGSMITH_API_KEY"
        ),
    }


def langfuse_status() -> dict[str, Any]:
    host = os.getenv("LANGFUSE_HOST", "http://localhost:3002").rstrip("/")
    enabled = _env_bool("LANGFUSE_TRACER_ENABLED")
    public_key_present = bool(os.getenv("LANGFUSE_PUBLIC_KEY"))
    secret_key_present = bool(os.getenv("LANGFUSE_SECRET_KEY"))
    health = _http_health(f"{host}/api/public/health")
    return {
        "tool": "langfuse",
        "package_version": _version("langfuse"),
        "installed": _version("langfuse") is not None,
        "tracer_enabled_env": enabled,
        "public_key_present": public_key_present,
        "secret_key_present": secret_key_present,
        "host": host,
        "health": health,
        "offline_safe": True,
        "ready": (
            _version("langfuse") is not None
            and enabled
            and public_key_present
            and secret_key_present
            and health["healthy"]
        ),
        "mode": "self_hosted",
        "note": (
            "Langfuse service reachable; tracer waits for opt-in keys"
            if health["healthy"] and not (enabled and public_key_present and secret_key_present)
            else "Langfuse tracer ready"
            if health["healthy"]
            else "Langfuse service is not reachable from this host"
        ),
    }


def status() -> dict[str, Any]:
    langsmith = langsmith_status()
    langfuse = langfuse_status()
    return {
        "langsmith": langsmith,
        "langfuse": langfuse,
        "recommendation": (
            "Use Langfuse as the default OSS/self-hosted LLM observability plane; "
            "enable LangSmith only when managed LangChain-native tracing/eval is required."
        ),
        "overall": {
            "packages_installed": bool(langsmith["installed"] and langfuse["installed"]),
            "local_llm_observability_reachable": bool(langfuse["health"]["healthy"]),
            "managed_tracing_ready": bool(langsmith["ready"]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = status()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Langfuse: installed={payload['langfuse']['installed']} health={payload['langfuse']['health']['http_status']}")
        print(f"LangSmith: installed={payload['langsmith']['installed']} ready={payload['langsmith']['ready']}")
        print(payload["recommendation"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
