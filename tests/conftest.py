from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models.schemas import (
    CoolifyApplicationRequest,
    DeploymentProvider,
    ProjectDeployResponse,
    RagSyncManifest,
    RagSyncResponse,
    RagSyncStatus,
    ReadmeUpdateCheck,
)
from app.services.project_policy_service import ProjectPolicyService
from app.services.public_app_service import PublicAppService
from app.services.public_route_service import PublicRouteConfig, PublicRouteService
from app.services.rag_sync_service import RagSyncService
from app.services.registry_service import RegistryService
from app.services.template_service import TemplateService
from app.services.project_service import ProjectService
from app.storage.db import Database


class FakeRagSyncService:
    def __init__(self, repo_root: Path, rag_manifest_root: str):
        self.repo_root = repo_root
        self.manifest_dir = repo_root / rag_manifest_root
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self._state: dict[str, RagSyncResponse] = {}
        self._manifests: dict[str, RagSyncManifest] = {}
        self.deleted_documents: list[str] = []
        self.deletion_notes: list[dict[str, str]] = []

    def manifest_path(self, slug: str) -> Path:
        return self.manifest_dir / f"{slug}.yaml"

    def build_signature(self, source_paths: list[Path]) -> str:
        return "sig-" + "-".join(path.name for path in source_paths)

    def current_manifest(self, slug: str):
        return self._manifests.get(slug)

    def check_refresh_needed(self, slug: str, source_paths: list[Path]) -> ReadmeUpdateCheck:
        return ReadmeUpdateCheck(slug=slug, needs_refresh=slug not in self._state, reason="test-check", tracked_files=[str(p) for p in source_paths])

    def sync(self, slug: str, source_paths: list[Path], metadata: dict[str, str], force: bool = False, note: str | None = None) -> RagSyncResponse:
        metadata = {"tenant_id": "ui-projects", **metadata}
        response = RagSyncResponse(
            slug=slug,
            synced=True,
            rag_sync_status=RagSyncStatus.in_sync,
            signature=self.build_signature(source_paths),
            document_id=f"doc-{slug}",
            source_paths=[str(path.relative_to(self.repo_root)) for path in source_paths],
            details={"metadata": metadata, "force": force, "note": note},
        )
        self._state[slug] = response
        manifest = RagSyncManifest(
            slug=slug,
            source_paths=response.source_paths,
            last_sync_at=datetime.now(timezone.utc),
            rag_sync_status=RagSyncStatus.in_sync,
            signature=response.signature,
            document_id=response.document_id,
            notes=note,
        )
        self._manifests[slug] = manifest
        self.manifest_path(slug).write_text("slug: %s\n" % slug, encoding="utf-8")
        return response

    def delete_document(self, document_id: str, tenant_id: str | None = None) -> dict[str, object]:
        self.deleted_documents.append(document_id)
        return {"ok": True, "deleted": True, "document_id": document_id, "tenant_id": tenant_id}

    def write_deletion_note(
        self,
        *,
        slug: str,
        delete_mode: str,
        tenant_id: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, object]:
        doc_id = f"doc-delete-{slug}"
        self.deletion_notes.append({"slug": slug, "delete_mode": delete_mode, "tenant_id": tenant_id or ""})
        return {"ok": True, "document_id": doc_id, "tenant_id": tenant_id, "metadata": metadata or {}}


class FakeCoolifyService:
    def __init__(self):
        self.deploy_calls: list[CoolifyApplicationRequest] = []

    def list_projects(self):
        return {"projects": [], "count": 0}

    def health(self):
        return {
            "enabled": True,
            "configured": True,
            "reachable": True,
            "base_url": "http://coolify.test",
            "project_count": 1,
        }

    def resources(self):
        return {
            "health": self.health(),
            "projects": {"projects": [], "count": 0},
            "default_project_name": "ui-factory-prod",
            "default_environment_name": "production",
        }

    def deploy_project(self, request: CoolifyApplicationRequest, project_repo_root: Path) -> ProjectDeployResponse:
        self.deploy_calls.append(request)
        return ProjectDeployResponse(
            slug=request.slug,
            provider=DeploymentProvider.coolify,
            deployed=False,
            status="deploying",
            details={
                "application_uuid": f"coolify-{request.slug}",
                "project_name": request.project_name,
                "base_directory": request.base_directory,
                "repo_root": project_repo_root.name,
            },
        )


def seed_monorepo(repo_root: Path) -> None:
    (repo_root / "apps").mkdir(parents=True, exist_ok=True)
    (repo_root / "sandboxes").mkdir(parents=True, exist_ok=True)
    (repo_root / "registry" / "projects").mkdir(parents=True, exist_ok=True)
    (repo_root / "rag" / "manifests").mkdir(parents=True, exist_ok=True)
    templates = {
        "nextjs-starter": {
            "app/page.tsx": "export default function Page(){return <main>next</main>}\n",
            "package.json": '{"name":"nextjs-starter"}\n',
        },
        "react-starter": {
            "src/main.jsx": "console.log(\"react\")\n",
            "package.json": '{"name":"react-starter"}\n',
            "index.html": "<div id=\"root\"></div>\n",
        },
        "static-html-starter": {
            "index.html": "<h1>static</h1>\n",
            "Dockerfile": "FROM nginx:alpine\nCOPY . /usr/share/nginx/html\n",
        },
    }
    for slug, files in templates.items():
        base = repo_root / "templates" / slug / "scaffold"
        base.mkdir(parents=True, exist_ok=True)
        for rel, content in files.items():
            path = base / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


@pytest.fixture()
def project_service(tmp_path: Path) -> ProjectService:
    repo_root = tmp_path / "coolify-server"
    seed_monorepo(repo_root)
    db = Database(tmp_path / "hapi.db")
    db.init()
    policy = ProjectPolicyService(
        project_layout_path=Path("/home/juan/Documents/hapi/app/policies/project_layout_policy.yaml"),
        template_policy_path=Path("/home/juan/Documents/hapi/app/policies/template_policy.yaml"),
        registry_policy_path=Path("/home/juan/Documents/hapi/app/policies/registry_policy.yaml"),
        rag_sync_policy_path=Path("/home/juan/Documents/hapi/app/policies/rag_sync_policy.yaml"),
        coolify_policy_path=Path("/home/juan/Documents/hapi/app/policies/coolify_policy.yaml"),
    )
    registry = RegistryService(repo_root=repo_root, registry_root=policy.project_layout.registry_root)
    template = TemplateService(repo_root=repo_root, templates_root=policy.project_layout.templates_root)
    rag = FakeRagSyncService(repo_root=repo_root, rag_manifest_root=policy.project_layout.rag_root)
    coolify = FakeCoolifyService()
    public_route = PublicRouteService(
        config=PublicRouteConfig(
            enabled=False,
            ssh_host="",
            ssh_user="",
            ssh_key_path="",
            remote_traefik_root="",
            remote_dynamic_dir="",
            coolify_network="coolify",
        )
    )
    public_apps = PublicAppService(db=db, coolify_service=coolify)
    return ProjectService(
        db=db,
        default_ttl_hours=24,
        repo_root=repo_root,
        policy_service=policy,
        registry_service=registry,
        template_service=template,
        rag_sync_service=rag,
        coolify_service=coolify,
        public_route_service=public_route,
        public_app_service=public_apps,
    )
