from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.services.coolify_service import CoolifyConfig, CoolifyService
from app.services.discovery_service import DiscoveryService
from app.services.docker_client import DockerCli
from app.services.inventory_service import InventoryService
from app.services.policy_service import ServiceMutabilityPolicyService
from app.services.project_policy_service import ProjectPolicyService
from app.services.project_service import ProjectService
from app.services.rag_sync_service import RagSyncService
from app.services.registry_service import RegistryService
from app.services.service_manager import ServiceManager
from app.services.template_service import TemplateService
from app.storage.db import Database


@dataclass
class AppContainer:
    settings: Settings
    db: Database
    policy_service: ServiceMutabilityPolicyService
    project_policy_service: ProjectPolicyService
    docker_cli: DockerCli
    discovery_service: DiscoveryService
    inventory_service: InventoryService
    project_service: ProjectService
    service_manager: ServiceManager
    registry_service: RegistryService
    template_service: TemplateService
    rag_sync_service: RagSyncService
    coolify_service: CoolifyService


def build_container(settings: Settings) -> AppContainer:
    db = Database(settings.db_path)
    db.init()
    policy_service = ServiceMutabilityPolicyService(settings.service_mutability_policy_path)
    project_policy_service = ProjectPolicyService(
        project_layout_path=settings.project_layout_policy_path,
        template_policy_path=settings.template_policy_path,
        registry_policy_path=settings.registry_policy_path,
        rag_sync_policy_path=settings.rag_sync_policy_path,
        coolify_policy_path=settings.coolify_policy_path,
    )
    docker_cli = DockerCli(timeout=settings.discovery_timeout_seconds)
    discovery_service = DiscoveryService(docker_cli=docker_cli, policy_service=policy_service)
    inventory_service = InventoryService(db=db)
    registry_service = RegistryService(
        repo_root=settings.coolify_server_repo_root,
        registry_root=project_policy_service.project_layout.registry_root,
    )
    template_service = TemplateService(
        repo_root=settings.coolify_server_repo_root,
        templates_root=project_policy_service.project_layout.templates_root,
    )
    rag_sync_service = RagSyncService(
        repo_root=settings.coolify_server_repo_root,
        rag_manifest_root=project_policy_service.project_layout.rag_root,
        policy=project_policy_service.rag_sync,
        base_url=settings.rag_api_base_url,
        enabled=settings.rag_sync_enabled,
    )
    coolify_service = CoolifyService(
        config=CoolifyConfig(
            enabled=settings.coolify_enabled and project_policy_service.coolify.enabled,
            base_url=settings.coolify_base_url,
            api_token=settings.coolify_api_token,
            default_project_name=project_policy_service.coolify.default_project_name,
            default_environment_name=project_policy_service.coolify.default_environment_name,
        )
    )
    project_service = ProjectService(
        db=db,
        default_ttl_hours=settings.short_lived_default_ttl_hours,
        repo_root=settings.coolify_server_repo_root,
        policy_service=project_policy_service,
        registry_service=registry_service,
        template_service=template_service,
        rag_sync_service=rag_sync_service,
        coolify_service=coolify_service,
    )
    service_manager = ServiceManager(docker_cli=docker_cli)
    return AppContainer(
        settings=settings,
        db=db,
        policy_service=policy_service,
        project_policy_service=project_policy_service,
        docker_cli=docker_cli,
        discovery_service=discovery_service,
        inventory_service=inventory_service,
        project_service=project_service,
        service_manager=service_manager,
        registry_service=registry_service,
        template_service=template_service,
        rag_sync_service=rag_sync_service,
        coolify_service=coolify_service,
    )
