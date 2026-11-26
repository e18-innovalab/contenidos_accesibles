"""Esquemas de respuesta para métricas del docente (sin exponer proveedor ni modelo de IA)."""

from typing import Literal
from pydantic import BaseModel, Field


class UserActivityStats(BaseModel):
    actions: int = 0
    analyses: int = 0
    mock_analyses: int = 0
    proposals: int = 0
    mock_proposals: int = 0
    decisions: dict[str, int] = Field(default_factory=dict)
    uploads: int = 0
    uploads_rejected: int = 0
    exports: int = 0
    downloads: int = 0
    shares_created: int = 0
    share_opens: int = 0
    shares_revoked: int = 0
    ai_calls: int = 0
    tokens: int = 0
    rate_limited: int = 0
    transformations: int = 0
    mock_transformations: int = 0
    transformations_failed: int = 0
    transformation_decisions: dict[str, int] = Field(default_factory=dict)


class UserRecentEvent(BaseModel):
    created_at: str
    action: str
    format: str | None = None
    detail: str | None = None
    adaptation_type: str | None = None
    mock: int = 0
    size_bytes: int | None = None
    score: int | None = None
    barriers: int | None = None
    latency_ms: int | None = None
    tokens: int = 0


class UserMetricsResponse(BaseModel):
    range: Literal["24h", "7d", "30d"]
    unit: str
    buckets: list[str] = Field(default_factory=list)
    tokens: list[int] = Field(default_factory=list)
    activity: dict[str, list[int]] = Field(default_factory=dict)
    in_range: UserActivityStats = Field(default_factory=UserActivityStats)
    all_time: UserActivityStats = Field(default_factory=UserActivityStats)
    formats: dict[str, dict[str, int]] = Field(default_factory=dict)
    adaptations: dict[str, dict[str, int]] = Field(default_factory=dict)
    transformations: dict[str, dict[str, int]] = Field(default_factory=dict)
    recent: list[UserRecentEvent] = Field(default_factory=list)
