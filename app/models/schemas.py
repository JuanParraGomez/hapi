from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


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


class DeploymentProvider(str, Enum):
    coolify = "coolify"
    docker = "docker"
    none = "none"


class ProjectStatus(str, Enum):
    draft = "draft"
    active = "active"
    sandbox = "sandbox"
    deployed = "deployed"
    archived = "archived"
    promoted = "promoted"
    ready_for_deploy = "ready_for_deploy"


class RagSyncStatus(str, Enum):
    disabled = "disabled"
    pending = "pending"
    in_sync = "in_sync"
    stale = "stale"
    error = "error"


class AppType(str, Enum):
    react = "react"
    nextjs = "nextjs"
    static_html = "static_html"
    generic = "generic"


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
    lifetime: ProjectLifetime
    description: str | None = None
    slug: str | None = None
    template: str | None = None
    ttl_hours: int | None = None
    project_root: str | None = None
    deployment_provider: DeploymentProvider | None = None
    domain: str | None = None
    rag_sync_enabled: bool | None = None
    deploy_now: bool = False
    notes: str | None = None

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = "-".join(part for part in value.strip().lower().replace("_", "-").split("-") if part)
        if not normalized:
            raise ValueError("slug_empty")
        return normalized


class ProjectEditContextRequest(BaseModel):
    include_readme: bool = True


class ProjectPromoteRequest(BaseModel):
    target_slug: str | None = None
    domain: str | None = None
    deploy_now: bool = False
    notes: str | None = None


class ProjectDeployRequest(BaseModel):
    environment_profile: str = "production"
    domain: str | None = None
    force: bool = False


class ProjectRagSyncRequest(BaseModel):
    force: bool = False
    note: str | None = None


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


class TemplateDefinition(BaseModel):
    slug: str
    app_type: AppType = AppType.generic
    description: str = ""
    deployment_provider: DeploymentProvider = DeploymentProvider.coolify
    recommended_for: list[ProjectLifetime] = Field(default_factory=list)
    default_files: list[str] = Field(default_factory=list)


class ProjectLayoutPolicy(BaseModel):
    repo_root_name: str = "coolify-server"
    long_lived_root: str = "apps"
    short_lived_root: str = "sandboxes"
    registry_root: str = "registry/projects"
    rag_root: str = "rag/manifests"
    templates_root: str = "templates"
    required_files: list[str] = Field(default_factory=lambda: ["README.md", "app.meta.yaml", "deploy.meta.yaml"])
    allowed_roots: list[str] = Field(default_factory=lambda: ["apps", "sandboxes", "templates", "registry", "rag", "docs"])
    min_slug_length: int = 8
    min_slug_tokens: int = 2
    disallowed_slug_prefixes: list[str] = Field(
        default_factory=lambda: ["test", "tmp", "demo", "smoke", "probe", "repro", "hapi-ui", "hapi-app", "sales-probe"]
    )


class RegistryPolicy(BaseModel):
    source_of_truth: str = "registry/projects"
    require_readme: bool = True
    require_metadata: bool = True
    unique_slug: bool = True


class RagSyncPolicy(BaseModel):
    enabled: bool = True
    tracked_files: list[str] = Field(default_factory=lambda: ["README.md", "app.meta.yaml", "deploy.meta.yaml"])
    optional_files: list[str] = Field(default_factory=lambda: ["ARCHITECTURE.md", "DECISIONS.md"])
    conceptual_triggers: list[str] = Field(
        default_factory=lambda: [
            "purpose",
            "architecture",
            "domain",
            "stack",
            "deploy",
            "usage",
            "integration",
        ]
    )
    tenant_id: str = "ui-projects"
    delete_mode_default: str = "soft"
    hard_delete_prefixes: list[str] = Field(default_factory=lambda: ["qa-", "smoke-", "probe-", "repro-", "tmp-", "test-"])
    hard_delete_for_short_lived: bool = True


class CoolifyPolicy(BaseModel):
    enabled: bool = False
    default_project_name: str = "ui-factory-prod"
    default_environment_name: str = "production"
    admin_hosts: list[str] = Field(default_factory=list)
    prefer_for_long_lived_ui: bool = True


class ProjectRecord(BaseModel):
    project_id: str
    slug: str
    name: str
    description: str | None = None
    lifetime: ProjectLifetime
    status: ProjectStatus = ProjectStatus.draft
    template: str
    app_type: AppType = AppType.generic
    project_root: str
    repo_root: str = "coolify-server"
    deployment_provider: DeploymentProvider = DeploymentProvider.none
    domain: str | None = None
    coolify_project: str | None = None
    coolify_application: str | None = None
    rag_sync_enabled: bool = True
    rag_sync_status: RagSyncStatus = RagSyncStatus.pending
    ttl_hours: int | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    promoted_from: str | None = None
    created_by: str = "hapi"
    managed_by: str = "hapi"
    notes: str | None = None


class RegistryEntry(ProjectRecord):
    registry_path: str
    readme_path: str
    app_meta_path: str
    deploy_meta_path: str


class ProjectContextResponse(BaseModel):
    slug: str
    project_type: ProjectLifetime
    status: ProjectStatus
    project_root: str
    deployment_provider: DeploymentProvider
    domain: str | None = None
    template: str
    readme_summary: str
    rag_sync_status: RagSyncStatus
    metadata: dict[str, Any] = Field(default_factory=dict)
    notes_for_agent: list[str] = Field(default_factory=list)


class RegistryRefreshResponse(BaseModel):
    refreshed: int
    projects: list[RegistryEntry]


class ProjectDeployResponse(BaseModel):
    slug: str
    provider: DeploymentProvider
    deployed: bool
    status: str
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ProjectDeleteResponse(BaseModel):
    slug: str
    deleted: bool
    removed_paths: list[str] = Field(default_factory=list)
    coolify_deleted: bool = False
    public_registry_deleted: bool = False
    rag_action: str = "none"
    rag_deleted: bool = False
    rag_note_document_id: str | None = None
    rag_error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class RagSyncManifest(BaseModel):
    slug: str
    source_paths: list[str]
    last_sync_at: datetime | None = None
    rag_sync_status: RagSyncStatus = RagSyncStatus.pending
    signature: str | None = None
    document_id: str | None = None
    notes: str | None = None


class RagSyncResponse(BaseModel):
    slug: str
    synced: bool
    rag_sync_status: RagSyncStatus
    signature: str | None = None
    document_id: str | None = None
    source_paths: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class SlugValidationResponse(BaseModel):
    slug: str
    available: bool
    reason: str | None = None


class ProjectSummaryList(BaseModel):
    projects: list[ProjectRecord]
    count: int


class RegistryListResponse(BaseModel):
    projects: list[RegistryEntry]
    count: int


class CoolifyProjectInfo(BaseModel):
    uuid: str | None = None
    name: str
    environment_name: str | None = None
    application_name: str | None = None
    base_directory: str | None = None
    domain: str | None = None
    status: str | None = None


class CoolifyApplicationRequest(BaseModel):
    slug: str
    project_name: str
    environment_name: str
    app_type: AppType
    base_directory: str
    domain: str | None = None
    port: int | None = None


class CoolifyApplicationResponse(BaseModel):
    ok: bool
    project: CoolifyProjectInfo | None = None
    application_uuid: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class ProjectContextRenderRequest(BaseModel):
    slug: str


class ProjectLookupResponse(BaseModel):
    project: RegistryEntry


class ProjectPromoteResponse(BaseModel):
    previous_slug: str
    project: RegistryEntry
    deployed: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class CoolifyProjectsListResponse(BaseModel):
    projects: list[CoolifyProjectInfo] = Field(default_factory=list)
    count: int = 0


class ProjectPathValidation(BaseModel):
    path: str
    valid: bool
    reason: str | None = None


class ReadmeUpdateCheck(BaseModel):
    slug: str
    needs_refresh: bool
    reason: str
    tracked_files: list[str] = Field(default_factory=list)


class ProjectManifestFiles(BaseModel):
    readme: str
    app_meta: str
    deploy_meta: str
    registry_manifest: str
    rag_manifest: str


class ProjectCreationArtifacts(BaseModel):
    project: RegistryEntry
    files: ProjectManifestFiles
    deployed: bool = False
    deployment: ProjectDeployResponse | None = None
    rag_sync: RagSyncResponse | None = None


class ProjectUpdateRequest(BaseModel):
    description: str | None = None
    notes: str | None = None
    domain: str | None = None
    status: ProjectStatus | None = None
    rag_sync_enabled: bool | None = None

    @model_validator(mode="after")
    def require_any_field(self):
        if not any(getattr(self, field) is not None for field in ["description", "notes", "domain", "status", "rag_sync_enabled"]):
            raise ValueError("no_update_fields")
        return self


class PublicAppStatus(str, Enum):
    draft = "draft"
    building = "building"
    ready_for_deploy = "ready_for_deploy"
    deployed = "deployed"
    failed = "failed"
    archived = "archived"


class DeploymentStatus(str, Enum):
    pending = "pending"
    ready_for_coolify = "ready_for_coolify"
    deploying = "deploying"
    deployed = "deployed"
    failed = "failed"
    unknown = "unknown"


class SyncEventStatus(str, Enum):
    pending = "pending"
    synced = "synced"
    failed = "failed"


class PublicAppRecord(BaseModel):
    app_id: str
    slug: str
    name: str
    app_type: AppType = AppType.generic
    framework: str | None = None
    repo_url: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    public_url: str | None = None
    domain: str | None = None
    deployment_provider: DeploymentProvider = DeploymentProvider.coolify
    data_strategy: dict[str, Any] = Field(default_factory=dict)
    project_slug: str | None = None
    status: PublicAppStatus = PublicAppStatus.draft
    tags: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class PublicAppRegisterRequest(BaseModel):
    app_id: str | None = None
    slug: str
    name: str
    app_type: AppType = AppType.generic
    framework: str | None = None
    repo_url: str | None = None
    branch: str | None = None
    commit_sha: str | None = None
    public_url: str | None = None
    domain: str | None = None
    deployment_provider: DeploymentProvider = DeploymentProvider.coolify
    data_strategy: dict[str, Any] = Field(default_factory=dict)
    project_slug: str | None = None
    status: PublicAppStatus = PublicAppStatus.draft
    tags: list[str] = Field(default_factory=list)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None

    @field_validator("slug")
    @classmethod
    def normalize_public_slug(cls, value: str) -> str:
        normalized = "-".join(part for part in value.strip().lower().replace("_", "-").split("-") if part)
        if not normalized:
            raise ValueError("slug_empty")
        return normalized


class PublicAppDeploymentRequest(BaseModel):
    deployment_status: DeploymentStatus
    provider: DeploymentProvider = DeploymentProvider.coolify
    public_url: str | None = None
    domain: str | None = None
    commit_sha: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class PublicAppSyncRequest(BaseModel):
    target: str = "rag"
    status: SyncEventStatus = SyncEventStatus.synced
    details: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class PublicDeploymentRecord(BaseModel):
    app_id: str
    deployment_status: DeploymentStatus = DeploymentStatus.unknown
    provider: DeploymentProvider = DeploymentProvider.coolify
    public_url: str | None = None
    domain: str | None = None
    commit_sha: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime


class SyncEventRecord(BaseModel):
    event_id: str
    app_id: str
    target: str
    status: SyncEventStatus
    details: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    created_at: datetime


class PublicAppsListResponse(BaseModel):
    apps: list[PublicAppRecord] = Field(default_factory=list)
    count: int = 0


class PublicSummaryResponse(BaseModel):
    total_apps: int = 0
    deployed_apps: int = 0
    failed_apps: int = 0
    latest_apps: list[PublicAppRecord] = Field(default_factory=list)
    coolify: dict[str, Any] = Field(default_factory=dict)


class CoolifyHealthResponse(BaseModel):
    enabled: bool
    configured: bool
    reachable: bool
    base_url: str
    details: dict[str, Any] = Field(default_factory=dict)
