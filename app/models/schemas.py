from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Mutability(str, Enum):
    manageable = "manageable"
    read_only = "read_only"
    untouchable = "untouchable"


class Exposure(str, Enum):
    public = "public"
    internal = "internal"
    unknown = "unknown"


class Source(str, Enum):
    discovered = "discovered"
    configured = "configured"


class ServiceInventoryItem(BaseModel):
    service_id: str
    service_name: str
    source: Source = Source.discovered
    container_name: str | None = None
    image: str | None = None
    status: str | None = None
    ports: list[dict[str, Any]] = Field(default_factory=list)
    networks: list[str] = Field(default_factory=list)
    volumes: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    exposure: Exposure = Exposure.unknown
    mutability: Mutability = Mutability.read_only
    notes: str | None = None


class DiscoverySummary(BaseModel):
    discovered_at: datetime
    total_services: int
    public_services: int
    internal_services: int
    manageable_services: int
    read_only_services: int
    untouchable_services: int
    reverse_proxies: list[str] = Field(default_factory=list)


class DiscoveryResponse(BaseModel):
    summary: DiscoverySummary
    services: list[ServiceInventoryItem]


class ServiceActionRequest(BaseModel):
    action: str = Field(pattern="^(start|stop|restart)$")


class ServiceActionResponse(BaseModel):
    service_id: str
    action: str
    accepted: bool
    output: str | None = None
    error: str | None = None


class ProjectLifetime(str, Enum):
    short_lived = "short_lived"
    long_lived = "long_lived"


class ProjectCreateRequest(BaseModel):
    name: str
    description: str | None = None
    lifetime: ProjectLifetime
    ttl_hours: int | None = None


class ProjectRecord(BaseModel):
    project_id: str
    name: str
    description: str | None = None
    lifetime: ProjectLifetime
    ttl_hours: int | None = None
    created_at: datetime
    expires_at: datetime | None = None


class PolicyRule(BaseModel):
    match_name: str
    mutability: Mutability
    notes: str | None = None


class MutabilityPolicy(BaseModel):
    unknown_services: Mutability = Mutability.read_only
    service_rules: list[PolicyRule] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "hapi"
