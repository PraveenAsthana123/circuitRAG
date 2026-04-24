"""
Shared response schemas (Global CLAUDE.md §6 — API Design Standards).

Every service returns:

* :class:`SuccessResponse` for single-object success
* :class:`PaginatedResponse` for list endpoints
* :class:`ErrorResponse` on failure (via the exception handler)

Consistency makes client code trivial: front-end has ONE error-parser and
ONE pagination-handler.
"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    data: T
    correlation_id: str = Field(default="", description="Populated by middleware")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=500)
    has_more: bool = False
    correlation_id: str = Field(default="")


class ErrorResponse(BaseModel):
    detail: str
    error_code: str
    details: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(default="")


class HealthResponse(BaseModel):
    status: str = Field(description="'ok' or 'degraded'")
    service: str
    version: str = "0.1.0"
    checks: dict[str, str] = Field(default_factory=dict, description="dependency name → status")
