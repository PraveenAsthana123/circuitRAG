"""Inference-service configuration."""
from __future__ import annotations

from documind_core.config import BaseServiceSettings


class InferenceSettings(BaseServiceSettings):
    service_name: str = "inference-svc"

    # Where to reach retrieval-svc (internal mesh URL in prod)
    retrieval_svc_url: str = "http://localhost:8083"

    # Defaults; governance-svc can override per tenant
    prompt_version: str = "rag_answer_v1"
    max_new_tokens: int = 1024
    temperature: float = 0.1
