from __future__ import annotations

from pathlib import Path

import yaml

from app.models.schemas import Mutability, MutabilityPolicy, PolicyRule


class ServiceMutabilityPolicyService:
    def __init__(self, policy_path: Path):
        self.policy_path = policy_path
        self._policy = self._load()

    def _load(self) -> MutabilityPolicy:
        if not self.policy_path.exists():
            return MutabilityPolicy()
        raw = yaml.safe_load(self.policy_path.read_text(encoding="utf-8")) or {}
        defaults = raw.get("defaults", {})
        rules = [PolicyRule(**r) for r in raw.get("service_rules", [])]
        unknown = defaults.get("unknown_services", Mutability.read_only.value)
        return MutabilityPolicy(unknown_services=Mutability(unknown), service_rules=rules)

    def refresh(self) -> MutabilityPolicy:
        self._policy = self._load()
        return self._policy

    @property
    def policy(self) -> MutabilityPolicy:
        return self._policy

    def resolve_mutability(self, service_name: str) -> tuple[Mutability, str | None]:
        lowered = service_name.lower()
        for rule in self._policy.service_rules:
            if rule.match_name.lower() == lowered:
                return rule.mutability, rule.notes
        return self._policy.unknown_services, None
