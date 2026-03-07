from pathlib import Path

from app.models.schemas import Mutability
from app.services.discovery_service import DiscoveryService
from app.services.policy_service import ServiceMutabilityPolicyService


class FakeDocker:
    def list_containers(self):
        return [{"ID": "abc123", "Names": "n8n"}, {"ID": "def456", "Names": "redis"}]

    def inspect_container(self, container_id: str):
        if container_id == "abc123":
            return {
                "Name": "/n8n",
                "Config": {"Image": "n8nio/n8n", "Labels": {}},
                "State": {"Status": "running"},
                "NetworkSettings": {
                    "Ports": {"5678/tcp": [{"HostIp": "0.0.0.0", "HostPort": "5678"}]},
                    "Networks": {"default": {}},
                },
                "Mounts": [],
            }
        return {
            "Name": "/redis",
            "Config": {"Image": "redis:7", "Labels": {}},
            "State": {"Status": "running"},
            "NetworkSettings": {"Ports": {}, "Networks": {"default": {}}},
            "Mounts": [],
        }


def test_policy_defaults_and_explicit_rules(tmp_path: Path):
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        """
defaults:
  unknown_services: read_only
service_rules:
  - match_name: n8n
    mutability: manageable
""".strip()
    )
    policy = ServiceMutabilityPolicyService(policy_path)

    mutability_n8n, _ = policy.resolve_mutability("n8n")
    mutability_unknown, _ = policy.resolve_mutability("postgres")

    assert mutability_n8n == Mutability.manageable
    assert mutability_unknown == Mutability.read_only


def test_discovery_applies_mutability_and_exposure(tmp_path: Path):
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        """
defaults:
  unknown_services: read_only
service_rules:
  - match_name: n8n
    mutability: manageable
  - match_name: my-video
    mutability: manageable
""".strip()
    )

    discovery = DiscoveryService(FakeDocker(), ServiceMutabilityPolicyService(policy_path))
    result = discovery.run()

    services = {s.service_name: s for s in result.services}
    assert services["n8n"].mutability == Mutability.manageable
    assert services["redis"].mutability == Mutability.read_only
    assert services["n8n"].exposure.value == "public"
    assert services["redis"].exposure.value == "internal"
