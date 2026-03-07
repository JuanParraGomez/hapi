from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.models.schemas import (
    CoolifyProjectsListResponse,
    DiscoveryResponse,
    HealthResponse,
    MutabilityPolicy,
    ProjectContextResponse,
    ProjectCreateRequest,
    ProjectCreationArtifacts,
    ProjectDeployRequest,
    ProjectDeployResponse,
    ProjectEditContextRequest,
    ProjectPromoteRequest,
    ProjectPromoteResponse,
    ProjectRecord,
    ProjectRagSyncRequest,
    ProjectUpdateRequest,
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
