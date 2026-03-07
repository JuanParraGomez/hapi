from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.services.discovery_service import DiscoveryService
from app.services.docker_client import DockerCli
from app.services.inventory_service import InventoryService
from app.services.policy_service import ServiceMutabilityPolicyService
from app.services.project_service import ProjectService
from app.services.service_manager import ServiceManager
from app.storage.db import Database


@dataclass
class AppContainer:
    settings: Settings
    db: Database
    policy_service: ServiceMutabilityPolicyService
    docker_cli: DockerCli
    discovery_service: DiscoveryService
    inventory_service: InventoryService
    project_service: ProjectService
    service_manager: ServiceManager


def build_container(settings: Settings) -> AppContainer:
    db = Database(settings.db_path)
    db.init()
    policy_service = ServiceMutabilityPolicyService(settings.service_mutability_policy_path)
    docker_cli = DockerCli(timeout=settings.discovery_timeout_seconds)
    discovery_service = DiscoveryService(docker_cli=docker_cli, policy_service=policy_service)
    inventory_service = InventoryService(db=db)
    project_service = ProjectService(db=db, default_ttl_hours=settings.short_lived_default_ttl_hours)
    service_manager = ServiceManager(docker_cli=docker_cli)
    return AppContainer(
        settings=settings,
        db=db,
        policy_service=policy_service,
        docker_cli=docker_cli,
        discovery_service=discovery_service,
        inventory_service=inventory_service,
        project_service=project_service,
        service_manager=service_manager,
    )
