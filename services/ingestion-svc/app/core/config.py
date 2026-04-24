"""Ingestion-service configuration (subclasses the shared base)."""
from __future__ import annotations

from documind_core.config import BaseServiceSettings


class IngestionSettings(BaseServiceSettings):
    service_name: str = "ingestion-svc"

    # Parsing limits — protect against memory blow-ups on hostile uploads
    max_upload_mb: int = 50
    allowed_extensions: str = ".pdf,.docx,.txt,.md,.html"

    # Chunking defaults (tenant-overridable via governance policy)
    chunk_target_tokens: int = 512
    chunk_overlap_tokens: int = 50

    # Embedding batching
    embed_batch_size: int = 16

    # Saga
    saga_step_timeout_seconds: int = 60
    saga_total_timeout_seconds: int = 600

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [e.strip().lower() for e in self.allowed_extensions.split(",")]
