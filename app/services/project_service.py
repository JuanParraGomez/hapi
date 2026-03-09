from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import yaml

from app.models.schemas import (
    AppType,
    CoolifyApplicationRequest,
    DeploymentProvider,
    ProjectContextResponse,
    ProjectCreateRequest,
    ProjectCreationArtifacts,
    ProjectDeployRequest,
    ProjectDeployResponse,
    ProjectDeleteResponse,
    ProjectLifetime,
    ProjectManifestFiles,
    ProjectPromoteRequest,
    ProjectPromoteResponse,
    ProjectRecord,
    ProjectStatus,
    ProjectUpdateRequest,
    RagSyncResponse,
    RagSyncStatus,
    ReadmeUpdateCheck,
    RegistryEntry,
    RegistryRefreshResponse,
    SlugValidationResponse,
)
from app.services.coolify_service import CoolifyService
from app.services.project_policy_service import ProjectPolicyService
from app.services.public_app_service import PublicAppService
from app.services.public_route_service import PublicRouteService
from app.services.rag_sync_service import RagSyncService
from app.services.registry_service import RegistryService
from app.services.template_service import TemplateService
from app.storage.db import Database


class ProjectService:
    def __init__(
        self,
        db: Database,
        default_ttl_hours: int,
        repo_root: Path,
        policy_service: ProjectPolicyService,
        registry_service: RegistryService,
        template_service: TemplateService,
        rag_sync_service: RagSyncService,
        coolify_service: CoolifyService,
        public_route_service: PublicRouteService,
        public_app_service: PublicAppService,
    ):
        self.db = db
        self.default_ttl_hours = default_ttl_hours
        self.repo_root = repo_root
        self.policy_service = policy_service
        self.registry_service = registry_service
        self.template_service = template_service
        self.rag_sync_service = rag_sync_service
        self.coolify_service = coolify_service
        self.public_route_service = public_route_service
        self.public_app_service = public_app_service
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        policy = self.policy_service.project_layout
        if not self.repo_root.exists():
            raise ValueError(f"repo_root_not_available:{self.repo_root}")
        if not self.repo_root.is_dir():
            raise ValueError(f"repo_root_not_directory:{self.repo_root}")
        for relative in policy.allowed_roots:
            (self.repo_root / relative).mkdir(parents=True, exist_ok=True)
        (self.repo_root / policy.registry_root).mkdir(parents=True, exist_ok=True)
        (self.repo_root / policy.rag_root).mkdir(parents=True, exist_ok=True)
        self._ensure_file(self.repo_root / policy.long_lived_root / ".gitkeep", "")
        self._ensure_file(self.repo_root / policy.short_lived_root / ".gitkeep", "")
        self._ensure_readme(self.repo_root / policy.long_lived_root / "README.md", "Long-lived UI projects managed by hapi and Coolify.\n")
        self._ensure_readme(self.repo_root / policy.short_lived_root / "README.md", "Short-lived sandboxes managed by hapi.\n")
        self._ensure_readme(self.repo_root / "rag" / "README.md", "RAG manifests and sync metadata for UI projects.\n")
        self._ensure_readme(self.repo_root / policy.registry_root / "README.md", "Project registry manifests managed by hapi.\n")

    @staticmethod
    def _ensure_file(path: Path, content: str) -> None:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    @staticmethod
    def _ensure_readme(path: Path, content: str) -> None:
        if not path.exists():
            path.write_text(content, encoding="utf-8")

    @staticmethod
    def slugify(value: str) -> str:
        allowed = []
        for char in value.strip().lower():
            if char.isalnum():
                allowed.append(char)
            elif char in {" ", "_", "-"}:
                allowed.append("-")
        slug = "".join(allowed)
        while "--" in slug:
            slug = slug.replace("--", "-")
        slug = slug.strip("-")
        if not slug:
            raise ValueError("invalid_slug")
        return slug

    def _default_template(self, lifetime: ProjectLifetime) -> str:
        if lifetime == ProjectLifetime.long_lived:
            return "nextjs-starter"
        return "static-html-starter"

    def _default_provider(self, lifetime: ProjectLifetime) -> DeploymentProvider:
        if lifetime == ProjectLifetime.long_lived and self.policy_service.coolify.prefer_for_long_lived_ui:
            return DeploymentProvider.coolify
        if lifetime == ProjectLifetime.short_lived:
            return DeploymentProvider.docker
        return DeploymentProvider.none

    def _root_name(self, lifetime: ProjectLifetime) -> str:
        layout = self.policy_service.project_layout
        return layout.long_lived_root if lifetime == ProjectLifetime.long_lived else layout.short_lived_root

    def _project_dir(self, lifetime: ProjectLifetime, slug: str) -> Path:
        return self.repo_root / self._root_name(lifetime) / slug

    def validate_slug(self, slug: str) -> SlugValidationResponse:
        normalized = self.slugify(slug)
        policy = self.policy_service.project_layout
        tokens = [token for token in normalized.split("-") if token]
        if len(normalized) < policy.min_slug_length:
            return SlugValidationResponse(slug=normalized, available=False, reason="slug_too_short")
        if len(tokens) < policy.min_slug_tokens:
            return SlugValidationResponse(slug=normalized, available=False, reason="slug_not_indicative")
        for prefix in policy.disallowed_slug_prefixes:
            if normalized.startswith(prefix):
                return SlugValidationResponse(slug=normalized, available=False, reason=f"slug_prefix_disallowed:{prefix}")
        if self.registry_service.exists(normalized):
            return SlugValidationResponse(slug=normalized, available=False, reason="slug_already_exists")
        if (self.repo_root / self.policy_service.project_layout.long_lived_root / normalized).exists():
            return SlugValidationResponse(slug=normalized, available=False, reason="apps_path_exists")
        if (self.repo_root / self.policy_service.project_layout.short_lived_root / normalized).exists():
            return SlugValidationResponse(slug=normalized, available=False, reason="sandbox_path_exists")
        return SlugValidationResponse(slug=normalized, available=True)

    def create(self, request: ProjectCreateRequest) -> ProjectCreationArtifacts:
        now = datetime.now(timezone.utc)
        slug = self.slugify(request.slug or request.name)
        validation = self.validate_slug(slug)
        if not validation.available:
            raise ValueError(validation.reason)

        template_slug = request.template or self._default_template(request.lifetime)
        template = self.policy_service.template_by_slug(template_slug)
        provider = request.deployment_provider or self._default_provider(request.lifetime)
        project_dir = self._project_dir(request.lifetime, slug)
        project_dir.mkdir(parents=True, exist_ok=False)
        copied = self.template_service.copy_scaffold(template, project_dir)

        ttl_hours = request.ttl_hours
        expires_at = None
        status = ProjectStatus.active if request.lifetime == ProjectLifetime.long_lived else ProjectStatus.sandbox
        if request.lifetime == ProjectLifetime.short_lived:
            ttl_hours = ttl_hours or self.default_ttl_hours
            expires_at = now + timedelta(hours=ttl_hours)

        project_id = f"prj_{uuid.uuid4().hex[:12]}"
        domain = request.domain or self._default_domain(slug, request.lifetime)
        rag_enabled = self.policy_service.rag_sync.enabled if request.rag_sync_enabled is None else request.rag_sync_enabled
        project_root = str(project_dir.relative_to(self.repo_root))
        coolify_project = self.policy_service.coolify.default_project_name if provider == DeploymentProvider.coolify else None
        coolify_application = slug if provider == DeploymentProvider.coolify else None

        readme_path = project_dir / "README.md"
        app_meta_path = project_dir / "app.meta.yaml"
        deploy_meta_path = project_dir / "deploy.meta.yaml"
        readme_content = self._build_readme(
            slug=slug,
            name=request.name,
            description=request.description,
            lifetime=request.lifetime,
            template=template.slug,
            project_root=project_root,
            provider=provider,
            domain=domain,
            copied=copied,
        )
        readme_path.write_text(readme_content, encoding="utf-8")
        app_meta = {
            "project_id": project_id,
            "slug": slug,
            "name": request.name,
            "description": request.description,
            "project_type": request.lifetime.value,
            "status": status.value,
            "template": template.slug,
            "app_type": template.app_type.value,
            "repo_root": self.policy_service.project_layout.repo_root_name,
            "project_root": project_root,
            "deployment_provider": provider.value,
            "coolify_project": coolify_project,
            "coolify_application": coolify_application,
            "domain": domain,
            "rag_sync_enabled": rag_enabled,
            "rag_sync_status": RagSyncStatus.pending.value,
            "ttl_hours": ttl_hours,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None,
            "created_by": "hapi",
            "managed_by": "hapi",
            "notes": request.notes or "",
        }
        deploy_meta = {
            "provider": provider.value,
            "repo": self.policy_service.project_layout.repo_root_name,
            "base_directory": f"/{project_root}",
            "app_type": template.app_type.value,
            "autodeploy": provider == DeploymentProvider.coolify,
            "exposed": bool(domain),
            "environment_profile": "production" if request.lifetime == ProjectLifetime.long_lived else "sandbox",
        }
        app_meta_path.write_text(yaml.safe_dump(app_meta, sort_keys=False, allow_unicode=False), encoding="utf-8")
        deploy_meta_path.write_text(yaml.safe_dump(deploy_meta, sort_keys=False, allow_unicode=False), encoding="utf-8")

        entry = RegistryEntry(
            project_id=project_id,
            slug=slug,
            name=request.name,
            description=request.description,
            lifetime=request.lifetime,
            status=status,
            template=template.slug,
            app_type=template.app_type,
            project_root=project_root,
            repo_root=self.policy_service.project_layout.repo_root_name,
            deployment_provider=provider,
            domain=domain,
            coolify_project=coolify_project,
            coolify_application=coolify_application,
            rag_sync_enabled=rag_enabled,
            rag_sync_status=RagSyncStatus.pending,
            ttl_hours=ttl_hours,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            promoted_from=None,
            created_by="hapi",
            managed_by="hapi",
            notes=request.notes,
            registry_path=str(self.registry_service.manifest_path(slug).relative_to(self.repo_root)),
            readme_path=str(readme_path.relative_to(self.repo_root)),
            app_meta_path=str(app_meta_path.relative_to(self.repo_root)),
            deploy_meta_path=str(deploy_meta_path.relative_to(self.repo_root)),
        )
        self.registry_service.write(entry)
        self._store_project_summary(entry)

        rag_sync = self.sync_rag(slug, force=True) if rag_enabled else None
        project = self.get(slug)
        deployment = self.deploy(slug, ProjectDeployRequest(domain=domain)) if request.deploy_now else None
        return ProjectCreationArtifacts(
            project=project,
            files=ProjectManifestFiles(
                readme=entry.readme_path,
                app_meta=entry.app_meta_path,
                deploy_meta=entry.deploy_meta_path,
                registry_manifest=entry.registry_path,
                rag_manifest=str(self.rag_sync_service.manifest_path(slug).relative_to(self.repo_root)),
            ),
            deployed=bool(deployment and deployment.deployed),
            deployment=deployment,
            rag_sync=rag_sync,
        )

    def delete(self, slug: str, *, purge_coolify: bool = True, purge_public_registry: bool = True) -> ProjectDeleteResponse:
        entry = self.get(slug)
        removed_paths: list[str] = []
        details: dict[str, object] = {}

        if purge_coolify and entry.deployment_provider == DeploymentProvider.coolify:
            try:
                coolify = self.coolify_service.delete_application(
                    slug=entry.slug,
                    base_directory=f"/{entry.project_root}",
                    domain=entry.domain,
                )
            except Exception as exc:  # pragma: no cover - network/runtime variability
                coolify = {"deleted": False, "reason": "coolify_delete_unavailable", "error": str(exc)}
            details["coolify"] = coolify
            coolify_deleted = bool(coolify.get("deleted"))
        else:
            coolify_deleted = False

        if purge_public_registry:
            public_result = self.public_app_service.delete_by_project_slug(entry.slug)
            details["public_registry"] = public_result
            public_registry_deleted = bool(public_result.get("deleted"))
        else:
            public_registry_deleted = False

        project_dir = self.repo_root / entry.project_root
        if project_dir.exists():
            shutil.rmtree(project_dir)
            removed_paths.append(str(project_dir.relative_to(self.repo_root)))

        rag_manifest_path = self.rag_sync_service.manifest_path(entry.slug)
        if rag_manifest_path.exists():
            rag_manifest_path.unlink()
            removed_paths.append(str(rag_manifest_path.relative_to(self.repo_root)))

        registry_manifest = self.registry_service.manifest_path(entry.slug)
        if registry_manifest.exists():
            registry_manifest.unlink()
            removed_paths.append(str(registry_manifest.relative_to(self.repo_root)))

        with self.db.connect() as conn:
            conn.execute("DELETE FROM projects WHERE slug = ?", (entry.slug,))

        return ProjectDeleteResponse(
            slug=entry.slug,
            deleted=True,
            removed_paths=removed_paths,
            coolify_deleted=coolify_deleted,
            public_registry_deleted=public_registry_deleted,
            details=details,
        )

    def get(self, slug: str) -> RegistryEntry:
        entry = self.registry_service.get(self.slugify(slug))
        if not entry:
            raise KeyError("project_not_found")
        rag_manifest = self.rag_sync_service.current_manifest(entry.slug)
        if rag_manifest:
            entry.rag_sync_status = rag_manifest.rag_sync_status
        return entry

    def list(self) -> list[ProjectRecord]:
        return self.registry_service.list()

    def list_registry(self) -> list[RegistryEntry]:
        return self.registry_service.list()

    def refresh_registry(self) -> RegistryRefreshResponse:
        projects = self.registry_service.refresh_from_filesystem(self.policy_service.project_layout.repo_root_name)
        for project in projects:
            self._store_project_summary(project)
        return RegistryRefreshResponse(refreshed=len(projects), projects=projects)

    def render_context(self, slug: str) -> ProjectContextResponse:
        project = self.get(slug)
        readme_path = self.repo_root / project.readme_path
        readme = readme_path.read_text(encoding="utf-8")
        summary = self._summarize_readme(readme)
        notes = [
            f"project lives in {project.project_root}",
            "edit README when changing architecture or scope",
            "keep app.meta.yaml and deploy.meta.yaml aligned with README",
            "deploy through Coolify for long-lived UI projects",
        ]
        return ProjectContextResponse(
            slug=project.slug,
            project_type=project.lifetime,
            status=project.status,
            project_root=project.project_root,
            deployment_provider=project.deployment_provider,
            domain=project.domain,
            template=project.template,
            readme_summary=summary,
            rag_sync_status=project.rag_sync_status,
            metadata={
                "coolify_project": project.coolify_project,
                "coolify_application": project.coolify_application,
                "repo_root": project.repo_root,
                "readme_path": project.readme_path,
                "app_meta_path": project.app_meta_path,
                "deploy_meta_path": project.deploy_meta_path,
            },
            notes_for_agent=notes,
        )

    def update_project(self, slug: str, request: ProjectUpdateRequest) -> RegistryEntry:
        entry = self.get(slug)
        old_domain = entry.domain
        if request.description is not None:
            entry.description = request.description
        if request.notes is not None:
            entry.notes = request.notes
        if request.domain is not None:
            entry.domain = request.domain
        if request.status is not None:
            entry.status = request.status
        if request.rag_sync_enabled is not None:
            entry.rag_sync_enabled = request.rag_sync_enabled
        entry.updated_at = datetime.now(timezone.utc)
        self._write_project_metadata(entry)
        if old_domain != entry.domain:
            self._rewrite_readme(entry)
        self.registry_service.write(entry)
        self._store_project_summary(entry)
        return entry

    def promote(self, slug: str, request: ProjectPromoteRequest) -> ProjectPromoteResponse:
        entry = self.get(slug)
        if entry.lifetime != ProjectLifetime.short_lived:
            raise ValueError("project_is_not_short_lived")
        target_slug = self.slugify(request.target_slug or entry.slug)
        if target_slug != entry.slug:
            validation = self.validate_slug(target_slug)
            if not validation.available:
                raise ValueError(validation.reason)
        source_dir = self.repo_root / entry.project_root
        target_dir = self.repo_root / self.policy_service.project_layout.long_lived_root / target_slug
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_dir), str(target_dir))

        previous_slug = entry.slug
        promoted_from = entry.project_root
        entry.slug = target_slug
        entry.name = entry.name
        entry.lifetime = ProjectLifetime.long_lived
        entry.status = ProjectStatus.promoted
        entry.project_root = str(target_dir.relative_to(self.repo_root))
        entry.deployment_provider = DeploymentProvider.coolify
        entry.coolify_project = self.policy_service.coolify.default_project_name
        entry.coolify_application = target_slug
        entry.domain = request.domain or self._default_domain(target_slug, ProjectLifetime.long_lived)
        entry.expires_at = None
        entry.ttl_hours = None
        entry.promoted_from = promoted_from
        entry.updated_at = datetime.now(timezone.utc)
        entry.registry_path = str(self.registry_service.manifest_path(target_slug).relative_to(self.repo_root))
        entry.readme_path = str((target_dir / "README.md").relative_to(self.repo_root))
        entry.app_meta_path = str((target_dir / "app.meta.yaml").relative_to(self.repo_root))
        entry.deploy_meta_path = str((target_dir / "deploy.meta.yaml").relative_to(self.repo_root))
        if previous_slug != target_slug:
            self.registry_service.delete(previous_slug)
            old_rag_manifest = self.rag_sync_service.manifest_path(previous_slug)
            if old_rag_manifest.exists():
                old_rag_manifest.unlink()
        self._rewrite_readme(entry)
        self._write_project_metadata(entry)
        self.registry_service.write(entry)
        self._store_project_summary(entry)
        rag_sync = self.sync_rag(entry.slug, force=True)
        deployment = self.deploy(entry.slug, ProjectDeployRequest(domain=entry.domain)) if request.deploy_now else None
        details = {"rag_sync": rag_sync.model_dump(mode="json")}
        if deployment:
            details["deployment"] = deployment.model_dump(mode="json")
        return ProjectPromoteResponse(previous_slug=previous_slug, project=entry, deployed=bool(deployment and deployment.deployed), details=details)

    def deploy(self, slug: str, request: ProjectDeployRequest) -> ProjectDeployResponse:
        project = self.get(slug)
        if project.deployment_provider != DeploymentProvider.coolify:
            return ProjectDeployResponse(
                slug=slug,
                provider=project.deployment_provider,
                deployed=False,
                status="not_supported",
                error="deployment_provider_not_supported",
            )
        if request.domain:
            project.domain = request.domain
            project.updated_at = datetime.now(timezone.utc)
            self._write_project_metadata(project)
            self.registry_service.write(project)
            self._store_project_summary(project)
        coolify_request = CoolifyApplicationRequest(
            slug=project.slug,
            project_name=project.coolify_project or self.policy_service.coolify.default_project_name,
            environment_name=self.policy_service.coolify.default_environment_name,
            app_type=project.app_type,
            base_directory=f"/{project.project_root}",
            domain=project.domain,
            port=3000 if project.app_type == AppType.nextjs else 80,
        )
        try:
            deployment = self.coolify_service.deploy_project(coolify_request, self.repo_root)
        except httpx.HTTPStatusError as exc:
            details = {
                "coolify_http_status": exc.response.status_code,
                "coolify_response": (exc.response.text or "").strip()[:4000],
                "coolify_url": str(exc.request.url),
            }
            # Degraded mode: keep flow successful for orchestration and retry later.
            if exc.response.status_code in {502, 503, 504}:
                return ProjectDeployResponse(
                    slug=slug,
                    provider=DeploymentProvider.coolify,
                    deployed=False,
                    status="deferred",
                    error=None,
                    details={**details, "retry_recommended": True, "reason": "coolify_temporarily_unavailable"},
                )
            return ProjectDeployResponse(
                slug=slug,
                provider=DeploymentProvider.coolify,
                deployed=False,
                status="error",
                error="coolify_unavailable",
                details=details,
            )
        except Exception as exc:
            return ProjectDeployResponse(
                slug=slug,
                provider=DeploymentProvider.coolify,
                deployed=False,
                status="error",
                error="coolify_deploy_unexpected_error",
                details={"message": str(exc)},
            )
        application_uuid = deployment.details.get("application_uuid") if deployment.details else None
        if application_uuid:
            project.coolify_application = application_uuid
        if deployment.deployed and project.domain and application_uuid:
            try:
                route = self.public_route_service.publish_route(
                    slug=project.slug,
                    domain=project.domain,
                    application_uuid=application_uuid,
                    port=3000 if project.app_type == AppType.nextjs else 80,
                )
                deployment.details["public_route"] = route
            except Exception as exc:
                deployment.deployed = False
                deployment.status = "error"
                deployment.error = f"public_route_sync_failed:{exc}"
        if deployment.status in {"ready_for_coolify", "deploying", "deployed"}:
            project.status = ProjectStatus.ready_for_deploy if not deployment.deployed else ProjectStatus.deployed
            project.updated_at = datetime.now(timezone.utc)
            self._write_project_metadata(project)
            self.registry_service.write(project)
            self._store_project_summary(project)
        public_app = self.public_app_service.get_by_slug(project.slug)
        if public_app:
            from app.models.schemas import DeploymentStatus, PublicAppDeploymentRequest
            if deployment.status == "deployed":
                deployment_status = DeploymentStatus.deployed
            elif deployment.status == "deploying":
                deployment_status = DeploymentStatus.deploying
            elif deployment.status == "ready_for_coolify":
                deployment_status = DeploymentStatus.ready_for_coolify
            else:
                deployment_status = DeploymentStatus.failed
            self.public_app_service.record_deployment(
                public_app.app_id,
                PublicAppDeploymentRequest(
                    deployment_status=deployment_status,
                    provider=project.deployment_provider,
                    public_url=project.domain and f"https://{project.domain}",
                    domain=project.domain,
                    details=deployment.details,
                ),
            )
        return deployment

    def rag_status(self, slug: str) -> RagSyncResponse:
        project = self.get(slug)
        source_paths = self._rag_source_paths(project)
        manifest = self.rag_sync_service.current_manifest(project.slug)
        signature = self.rag_sync_service.build_signature(source_paths)
        if not manifest:
            return RagSyncResponse(
                slug=project.slug,
                synced=False,
                rag_sync_status=RagSyncStatus.pending if project.rag_sync_enabled else RagSyncStatus.disabled,
                signature=signature,
                source_paths=[str(path.relative_to(self.repo_root)) for path in source_paths],
            )
        return RagSyncResponse(
            slug=project.slug,
            synced=manifest.rag_sync_status == RagSyncStatus.in_sync,
            rag_sync_status=manifest.rag_sync_status,
            signature=manifest.signature or signature,
            document_id=manifest.document_id,
            source_paths=manifest.source_paths,
        )

    def sync_rag(self, slug: str, force: bool = False, note: str | None = None) -> RagSyncResponse:
        project = self.get(slug)
        source_paths = self._rag_source_paths(project)
        metadata = {
            "artifact_type": "ui_project_docs",
            "project_slug": project.slug,
            "project_type": project.lifetime.value,
            "deployment_provider": project.deployment_provider.value,
            "domain": project.domain or "",
            "template": project.template,
            "source_service": "hapi",
        }
        result = self.rag_sync_service.sync(project.slug, source_paths, metadata, force=force, note=note)
        project.rag_sync_status = result.rag_sync_status
        project.updated_at = datetime.now(timezone.utc)
        self._write_project_metadata(project)
        self.registry_service.write(project)
        self._store_project_summary(project)
        return result

    def check_conceptual_change(self, slug: str) -> ReadmeUpdateCheck:
        project = self.get(slug)
        return self.rag_sync_service.check_refresh_needed(project.slug, self._rag_source_paths(project))

    def _default_domain(self, slug: str, lifetime: ProjectLifetime) -> str | None:
        if lifetime == ProjectLifetime.long_lived:
            return f"{slug}.apps.uniflexa.cloud"
        return f"{slug}.sandbox.uniflexa.cloud"

    def _build_readme(
        self,
        slug: str,
        name: str,
        description: str | None,
        lifetime: ProjectLifetime,
        template: str,
        project_root: str,
        provider: DeploymentProvider,
        domain: str | None,
        copied: list[str],
    ) -> str:
        copied_lines = "\n".join(f"- `{item}`" for item in copied) if copied else "- template scaffold empty; metadata-only bootstrap"
        return (
            f"# {name}\n\n"
            f"## Purpose\n{description or 'Document the purpose of this project here.'}\n\n"
            f"## Project Identity\n"
            f"- slug: `{slug}`\n"
            f"- project_type: `{lifetime.value}`\n"
            f"- template: `{template}`\n"
            f"- project_root: `{project_root}`\n"
            f"- deployment_provider: `{provider.value}`\n"
            f"- domain: `{domain or 'pending'}`\n\n"
            f"## How It Should Be Managed\n"
            f"- This project lives inside the `coolify-server` monorepo.\n"
            f"- Update this README whenever purpose, architecture, deployment or usage changes.\n"
            f"- Keep `app.meta.yaml` and `deploy.meta.yaml` aligned with this file.\n\n"
            f"## Initial Scaffold\n{copied_lines}\n"
        )

    def _summarize_readme(self, readme: str) -> str:
        lines = [line.strip() for line in readme.splitlines() if line.strip()]
        summary_parts = []
        for line in lines:
            if line.startswith("#"):
                continue
            summary_parts.append(line)
            if len(" ".join(summary_parts)) > 280:
                break
        return " ".join(summary_parts)[:320]

    def _rag_source_paths(self, project: RegistryEntry) -> list[Path]:
        base = self.repo_root / project.project_root
        paths = [base / item for item in self.policy_service.rag_sync.tracked_files]
        for optional in self.policy_service.rag_sync.optional_files:
            candidate = base / optional
            if candidate.exists():
                paths.append(candidate)
        return [path for path in paths if path.exists()]

    def _rewrite_readme(self, entry: RegistryEntry) -> None:
        readme_path = self.repo_root / entry.readme_path
        readme_path.write_text(
            self._build_readme(
                slug=entry.slug,
                name=entry.name,
                description=entry.description,
                lifetime=entry.lifetime,
                template=entry.template,
                project_root=entry.project_root,
                provider=entry.deployment_provider,
                domain=entry.domain,
                copied=[],
            ),
            encoding="utf-8",
        )

    def _write_project_metadata(self, entry: RegistryEntry) -> None:
        app_meta_path = self.repo_root / entry.app_meta_path
        deploy_meta_path = self.repo_root / entry.deploy_meta_path
        app_meta = {
            "project_id": entry.project_id,
            "slug": entry.slug,
            "name": entry.name,
            "description": entry.description,
            "project_type": entry.lifetime.value,
            "status": entry.status.value,
            "template": entry.template,
            "app_type": entry.app_type.value,
            "repo_root": entry.repo_root,
            "project_root": entry.project_root,
            "deployment_provider": entry.deployment_provider.value,
            "coolify_project": entry.coolify_project,
            "coolify_application": entry.coolify_application,
            "domain": entry.domain,
            "rag_sync_enabled": entry.rag_sync_enabled,
            "rag_sync_status": entry.rag_sync_status.value,
            "ttl_hours": entry.ttl_hours,
            "created_at": entry.created_at.isoformat(),
            "updated_at": entry.updated_at.isoformat(),
            "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
            "promoted_from": entry.promoted_from,
            "created_by": entry.created_by,
            "managed_by": entry.managed_by,
            "notes": entry.notes or "",
        }
        deploy_meta = {
            "provider": entry.deployment_provider.value,
            "repo": entry.repo_root,
            "base_directory": f"/{entry.project_root}",
            "app_type": entry.app_type.value,
            "autodeploy": entry.deployment_provider == DeploymentProvider.coolify,
            "exposed": bool(entry.domain),
            "environment_profile": "production" if entry.lifetime == ProjectLifetime.long_lived else "sandbox",
        }
        app_meta_path.write_text(yaml.safe_dump(app_meta, sort_keys=False, allow_unicode=False), encoding="utf-8")
        deploy_meta_path.write_text(yaml.safe_dump(deploy_meta, sort_keys=False, allow_unicode=False), encoding="utf-8")

    def _store_project_summary(self, project: RegistryEntry) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    project_id, slug, name, description, lifetime, ttl_hours, created_at, updated_at,
                    expires_at, status, project_root, template, deployment_provider, domain,
                    rag_sync_enabled, promoted_from
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    slug=excluded.slug,
                    name=excluded.name,
                    description=excluded.description,
                    lifetime=excluded.lifetime,
                    ttl_hours=excluded.ttl_hours,
                    updated_at=excluded.updated_at,
                    expires_at=excluded.expires_at,
                    status=excluded.status,
                    project_root=excluded.project_root,
                    template=excluded.template,
                    deployment_provider=excluded.deployment_provider,
                    domain=excluded.domain,
                    rag_sync_enabled=excluded.rag_sync_enabled,
                    promoted_from=excluded.promoted_from
                """,
                (
                    project.project_id,
                    project.slug,
                    project.name,
                    project.description,
                    project.lifetime.value,
                    project.ttl_hours,
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                    project.expires_at.isoformat() if project.expires_at else None,
                    project.status.value,
                    project.project_root,
                    project.template,
                    project.deployment_provider.value,
                    project.domain,
                    1 if project.rag_sync_enabled else 0,
                    project.promoted_from,
                ),
            )
