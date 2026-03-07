from __future__ import annotations

from app.models.schemas import ServiceActionResponse, ServiceInventoryItem
from app.services.docker_client import DockerCli


class ServiceManager:
    def __init__(self, docker_cli: DockerCli):
        self.docker_cli = docker_cli

    def execute(self, service: ServiceInventoryItem, action: str) -> ServiceActionResponse:
        if service.mutability.value != "manageable":
            return ServiceActionResponse(
                service_id=service.service_id,
                action=action,
                accepted=False,
                error=f"service mutability={service.mutability.value}; action denied",
            )

        container_name = service.container_name or service.service_name
        result = self.docker_cli.service_action(container_name=container_name, action=action)
        return ServiceActionResponse(
            service_id=service.service_id,
            action=action,
            accepted=result.ok,
            output=(result.stdout or "").strip() or None,
            error=(result.stderr or "").strip() or None,
        )
