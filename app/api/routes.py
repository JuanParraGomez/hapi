from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.models.schemas import (
    DiscoveryResponse,
    HealthResponse,
    MutabilityPolicy,
    ProjectCreateRequest,
    ProjectRecord,
    ServiceActionRequest,
    ServiceActionResponse,
    ServiceInventoryItem,
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
def service_action(
    service_id: str,
    request: ServiceActionRequest,
    container=Depends(get_container),
) -> ServiceActionResponse:
    service = container.inventory_service.service_by_id(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="service_not_found")
    result = container.service_manager.execute(service, request.action)
    if not result.accepted:
        raise HTTPException(status_code=403, detail=result.error or "action_denied")
    return result


@router.post("/projects", response_model=ProjectRecord)
def create_project(request: ProjectCreateRequest, container=Depends(get_container)) -> ProjectRecord:
    return container.project_service.create(request)


@router.get("/projects", response_model=list[ProjectRecord])
def list_projects(container=Depends(get_container)) -> list[ProjectRecord]:
    return container.project_service.list()
