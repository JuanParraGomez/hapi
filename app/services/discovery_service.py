from __future__ import annotations

from datetime import datetime, timezone

from app.models.schemas import DiscoveryResponse, DiscoverySummary, Exposure, ServiceInventoryItem, Source
from app.services.docker_client import DockerCli
from app.services.policy_service import ServiceMutabilityPolicyService


class DiscoveryService:
    def __init__(self, docker_cli: DockerCli, policy_service: ServiceMutabilityPolicyService):
        self.docker_cli = docker_cli
        self.policy_service = policy_service

    def run(self) -> DiscoveryResponse:
        containers = self.docker_cli.list_containers()
        services: list[ServiceInventoryItem] = []
        reverse_proxies: list[str] = []

        for row in containers:
            container_id = row.get("ID", "")
            inspect = self.docker_cli.inspect_container(container_id) or {}
            name = (inspect.get("Name") or row.get("Names") or "").strip("/")
            service_name = name or row.get("Names") or container_id[:12]
            image = inspect.get("Config", {}).get("Image") or row.get("Image")
            state = inspect.get("State", {}).get("Status") or row.get("State")
            network_settings = inspect.get("NetworkSettings", {})
            ports_raw = network_settings.get("Ports") or {}
            ports = self._extract_ports(ports_raw)
            networks = list((network_settings.get("Networks") or {}).keys())
            mounts = inspect.get("Mounts") or []
            volumes = [m.get("Name") or m.get("Source") or "" for m in mounts if m]
            labels = inspect.get("Config", {}).get("Labels") or {}

            exposure = self._classify_exposure(ports)
            mutability, notes = self.policy_service.resolve_mutability(service_name)

            if self._looks_like_proxy(service_name, image, labels):
                reverse_proxies.append(service_name)

            services.append(
                ServiceInventoryItem(
                    service_id=container_id[:12] or service_name,
                    service_name=service_name,
                    source=Source.discovered,
                    container_name=name,
                    image=image,
                    status=state,
                    ports=ports,
                    networks=networks,
                    volumes=volumes,
                    labels={str(k): str(v) for k, v in labels.items()},
                    exposure=exposure,
                    mutability=mutability,
                    notes=notes,
                )
            )

        summary = DiscoverySummary(
            discovered_at=datetime.now(timezone.utc),
            total_services=len(services),
            public_services=sum(1 for s in services if s.exposure == Exposure.public),
            internal_services=sum(1 for s in services if s.exposure == Exposure.internal),
            manageable_services=sum(1 for s in services if s.mutability.value == "manageable"),
            read_only_services=sum(1 for s in services if s.mutability.value == "read_only"),
            untouchable_services=sum(1 for s in services if s.mutability.value == "untouchable"),
            reverse_proxies=sorted(set(reverse_proxies)),
        )

        return DiscoveryResponse(summary=summary, services=services)

    @staticmethod
    def _extract_ports(ports_raw: dict) -> list[dict]:
        ports: list[dict] = []
        for container_port, bindings in ports_raw.items():
            if not bindings:
                ports.append({"container_port": container_port, "published": False})
                continue
            for bind in bindings:
                ports.append(
                    {
                        "container_port": container_port,
                        "host_ip": bind.get("HostIp"),
                        "host_port": bind.get("HostPort"),
                        "published": True,
                    }
                )
        return ports

    @staticmethod
    def _classify_exposure(ports: list[dict]) -> Exposure:
        if not ports:
            return Exposure.internal
        for p in ports:
            ip = p.get("host_ip")
            if ip in {"0.0.0.0", "::", "[::]"}:
                return Exposure.public
        return Exposure.internal

    @staticmethod
    def _looks_like_proxy(service_name: str, image: str | None, labels: dict) -> bool:
        candidate = f"{service_name} {image or ''}".lower()
        if any(k in candidate for k in ("traefik", "nginx", "caddy", "haproxy")):
            return True
        if any(str(k).startswith("traefik.http.routers") for k in labels):
            return True
        return False
