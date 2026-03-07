from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.models.schemas import ProjectRecord, RegistryEntry


class RegistryService:
    def __init__(self, repo_root: Path, registry_root: str):
        self.repo_root = repo_root
        self.registry_dir = repo_root / registry_root
        self.registry_dir.mkdir(parents=True, exist_ok=True)

    def manifest_path(self, slug: str) -> Path:
        return self.registry_dir / f"{slug}.yaml"

    def exists(self, slug: str) -> bool:
        return self.manifest_path(slug).exists()

    def write(self, record: RegistryEntry) -> RegistryEntry:
        path = self.manifest_path(record.slug)
        payload = record.model_dump(mode="json")
        path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")
        return record

    def get(self, slug: str) -> RegistryEntry | None:
        path = self.manifest_path(slug)
        if not path.exists():
            return None
        return RegistryEntry.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    def list(self) -> list[RegistryEntry]:
        items: list[RegistryEntry] = []
        for path in sorted(self.registry_dir.glob("*.yaml")):
            items.append(RegistryEntry.model_validate(yaml.safe_load(path.read_text(encoding="utf-8"))))
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    def delete(self, slug: str) -> None:
        path = self.manifest_path(slug)
        if path.exists():
            path.unlink()

    def refresh_from_filesystem(self, repo_root_name: str) -> list[RegistryEntry]:
        refreshed: list[RegistryEntry] = []
        for root_name in ("apps", "sandboxes"):
            root = self.repo_root / root_name
            if not root.exists():
                continue
            for project_dir in sorted(p for p in root.iterdir() if p.is_dir()):
                app_meta = project_dir / "app.meta.yaml"
                deploy_meta = project_dir / "deploy.meta.yaml"
                readme = project_dir / "README.md"
                if not (app_meta.exists() and deploy_meta.exists() and readme.exists()):
                    continue
                app_payload = yaml.safe_load(app_meta.read_text(encoding="utf-8")) or {}
                record = RegistryEntry(
                    project_id=app_payload["project_id"],
                    slug=app_payload["slug"],
                    name=app_payload.get("name", app_payload["slug"]),
                    description=app_payload.get("description"),
                    lifetime=app_payload["project_type"],
                    status=app_payload.get("status", "draft"),
                    template=app_payload["template"],
                    app_type=app_payload.get("app_type", "generic"),
                    project_root=app_payload["project_root"],
                    repo_root=repo_root_name,
                    deployment_provider=app_payload.get("deployment_provider", "none"),
                    domain=app_payload.get("domain"),
                    coolify_project=app_payload.get("coolify_project"),
                    coolify_application=app_payload.get("coolify_application"),
                    rag_sync_enabled=bool(app_payload.get("rag_sync_enabled", True)),
                    rag_sync_status=app_payload.get("rag_sync_status", "pending"),
                    ttl_hours=app_payload.get("ttl_hours"),
                    created_at=datetime.fromisoformat(app_payload["created_at"]),
                    updated_at=datetime.fromisoformat(app_payload.get("updated_at", app_payload["created_at"])),
                    expires_at=datetime.fromisoformat(app_payload["expires_at"]) if app_payload.get("expires_at") else None,
                    promoted_from=app_payload.get("promoted_from"),
                    created_by=app_payload.get("created_by", "hapi"),
                    managed_by=app_payload.get("managed_by", "hapi"),
                    notes=app_payload.get("notes"),
                    registry_path=str(self.manifest_path(app_payload["slug"]).relative_to(self.repo_root)),
                    readme_path=str(readme.relative_to(self.repo_root)),
                    app_meta_path=str(app_meta.relative_to(self.repo_root)),
                    deploy_meta_path=str(deploy_meta.relative_to(self.repo_root)),
                )
                self.write(record)
                refreshed.append(record)
        return refreshed

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)
