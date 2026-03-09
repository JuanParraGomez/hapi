from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.models.schemas import (
    CoolifyHealthResponse,
    CoolifyProjectsListResponse,
    DiscoveryResponse,
    HealthResponse,
    MutabilityPolicy,
    ProjectContextResponse,
    ProjectCreateRequest,
    ProjectCreationArtifacts,
    ProjectDeployRequest,
    ProjectDeployResponse,
    ProjectDeleteResponse,
    ProjectEditContextRequest,
    ProjectPromoteRequest,
    ProjectPromoteResponse,
    ProjectRecord,
    ProjectRagSyncRequest,
    ProjectUpdateRequest,
    PublicAppDeploymentRequest,
    PublicAppRecord,
    PublicAppsListResponse,
    PublicAppRegisterRequest,
    PublicAppSyncRequest,
    PublicDeploymentRecord,
    PublicSummaryResponse,
    RagSyncResponse,
    RegistryEntry,
    RegistryListResponse,
    RegistryRefreshResponse,
    ServiceActionRequest,
    ServiceActionResponse,
    ServiceInventoryItem,
    SlugValidationResponse,
)
from app.services.dependencies import get_container

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/policy/mutability", response_model=MutabilityPolicy)
def get_mutability_policy(container=Depends(get_container)) -> MutabilityPolicy:
    return container.policy_service.policy


@router.post("/discovery/run", response_model=DiscoveryResponse)
def run_discovery(container=Depends(get_container)) -> DiscoveryResponse:
    payload = container.discovery_service.run()
    container.inventory_service.store_run(payload)
    return payload


@router.get("/services", response_model=list[ServiceInventoryItem])
def list_services(container=Depends(get_container)) -> list[ServiceInventoryItem]:
    return container.inventory_service.latest_services()


@router.get("/services/{service_id}", response_model=ServiceInventoryItem)
def get_service(service_id: str, container=Depends(get_container)) -> ServiceInventoryItem:
    service = container.inventory_service.service_by_id(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="service_not_found")
    return service


@router.post("/services/{service_id}/actions", response_model=ServiceActionResponse)
def service_action(service_id: str, request: ServiceActionRequest, container=Depends(get_container)) -> ServiceActionResponse:
    service = container.inventory_service.service_by_id(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="service_not_found")
    result = container.service_manager.execute(service, request.action)
    if not result.accepted:
        raise HTTPException(status_code=403, detail=result.error or "action_denied")
    return result


@router.post("/projects", response_model=ProjectRecord)
def create_project_compat(request: ProjectCreateRequest, container=Depends(get_container)) -> ProjectRecord:
    try:
        return container.project_service.create(request).project
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/projects/create", response_model=ProjectCreationArtifacts)
def create_project(request: ProjectCreateRequest, container=Depends(get_container)) -> ProjectCreationArtifacts:
    try:
        return container.project_service.create(request)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/projects", response_model=list[ProjectRecord])
def list_projects(container=Depends(get_container)) -> list[ProjectRecord]:
    return container.project_service.list()


@router.get("/projects/{slug}", response_model=RegistryEntry)
def get_project(slug: str, container=Depends(get_container)) -> RegistryEntry:
    try:
        return container.project_service.get(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{slug}/validate", response_model=SlugValidationResponse)
def validate_project_slug(slug: str, container=Depends(get_container)) -> SlugValidationResponse:
    return container.project_service.validate_slug(slug)


@router.post("/projects/{slug}/edit-context", response_model=ProjectContextResponse)
def render_project_context(slug: str, _: ProjectEditContextRequest, container=Depends(get_container)) -> ProjectContextResponse:
    try:
        return container.project_service.render_context(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{slug}/deploy", response_model=ProjectDeployResponse)
def deploy_project(slug: str, request: ProjectDeployRequest, container=Depends(get_container)) -> ProjectDeployResponse:
    try:
        return container.project_service.deploy(slug, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/projects/{slug}", response_model=ProjectDeleteResponse)
def delete_project(
    slug: str,
    purge_coolify: bool = True,
    purge_public_registry: bool = True,
    container=Depends(get_container),
) -> ProjectDeleteResponse:
    try:
        return container.project_service.delete(
            slug,
            purge_coolify=purge_coolify,
            purge_public_registry=purge_public_registry,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{slug}/sync-rag", response_model=RagSyncResponse)
def sync_project_rag(slug: str, request: ProjectRagSyncRequest, container=Depends(get_container)) -> RagSyncResponse:
    try:
        return container.project_service.sync_rag(slug, force=request.force, note=request.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{slug}/rag-status", response_model=RagSyncResponse)
def project_rag_status(slug: str, container=Depends(get_container)) -> RagSyncResponse:
    try:
        return container.project_service.rag_status(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{slug}/promote", response_model=ProjectPromoteResponse)
def promote_project(slug: str, request: ProjectPromoteRequest, container=Depends(get_container)) -> ProjectPromoteResponse:
    try:
        return container.project_service.promote(slug, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/projects/{slug}", response_model=RegistryEntry)
def update_project(slug: str, request: ProjectUpdateRequest, container=Depends(get_container)) -> RegistryEntry:
    try:
        return container.project_service.update_project(slug, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/registry", response_model=RegistryListResponse)
def list_registry(container=Depends(get_container)) -> RegistryListResponse:
    projects = container.project_service.list_registry()
    return RegistryListResponse(projects=projects, count=len(projects))


@router.get("/registry/{slug}", response_model=RegistryEntry)
def get_registry_project(slug: str, container=Depends(get_container)) -> RegistryEntry:
    try:
        return container.project_service.get(slug)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/registry/refresh", response_model=RegistryRefreshResponse)
def refresh_registry(container=Depends(get_container)) -> RegistryRefreshResponse:
    return container.project_service.refresh_registry()


@router.get("/coolify/projects", response_model=CoolifyProjectsListResponse)
def list_coolify_projects(container=Depends(get_container)) -> CoolifyProjectsListResponse:
    return container.coolify_service.list_projects()


@router.get("/public/apps", response_model=PublicAppsListResponse)
def list_public_apps(container=Depends(get_container)) -> PublicAppsListResponse:
    return container.public_app_service.list_apps()


@router.get("/public/apps/{app_id}", response_model=PublicAppRecord)
def get_public_app(app_id: str, container=Depends(get_container)) -> PublicAppRecord:
    app = container.public_app_service.get_app(app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="public_app_not_found")
    return app


@router.get("/public/apps/by-slug/{slug}", response_model=PublicAppRecord)
def get_public_app_by_slug(slug: str, container=Depends(get_container)) -> PublicAppRecord:
    app = container.public_app_service.get_by_slug(slug)
    if app is None:
        raise HTTPException(status_code=404, detail="public_app_not_found")
    return app


@router.get("/public/apps/by-domain/{domain:path}", response_model=PublicAppRecord)
def get_public_app_by_domain(domain: str, container=Depends(get_container)) -> PublicAppRecord:
    app = container.public_app_service.get_by_domain(domain)
    if app is None:
        raise HTTPException(status_code=404, detail="public_app_not_found")
    return app


@router.post("/public/apps/register", response_model=PublicAppRecord)
def register_public_app(request: PublicAppRegisterRequest, container=Depends(get_container)) -> PublicAppRecord:
    return container.public_app_service.register(request)


@router.post("/public/apps/{app_id}/deployment", response_model=PublicDeploymentRecord)
def record_public_deployment(app_id: str, request: PublicAppDeploymentRequest, container=Depends(get_container)) -> PublicDeploymentRecord:
    try:
        return container.public_app_service.record_deployment(app_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/public/apps/{app_id}/sync")
def record_public_sync(app_id: str, request: PublicAppSyncRequest, container=Depends(get_container)) -> dict:
    try:
        event = container.public_app_service.record_sync(app_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "event": event.model_dump(mode="json")}


@router.get("/public/deployments/{app_id}/status", response_model=PublicDeploymentRecord)
def get_public_deployment_status(app_id: str, container=Depends(get_container)) -> PublicDeploymentRecord:
    deployment = container.public_app_service.deployment_status(app_id)
    if deployment is None:
        raise HTTPException(status_code=404, detail="public_deployment_not_found")
    return deployment


@router.get("/infra/coolify/health", response_model=CoolifyHealthResponse)
def coolify_health(container=Depends(get_container)) -> CoolifyHealthResponse:
    return container.public_app_service.coolify_health()


@router.get("/infra/coolify/resources")
def coolify_resources(container=Depends(get_container)) -> dict:
    return container.coolify_service.resources()


@router.get("/infra/public-summary", response_model=PublicSummaryResponse)
def public_summary(container=Depends(get_container)) -> PublicSummaryResponse:
    return container.public_app_service.public_summary()
