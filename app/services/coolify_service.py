from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from app.models.schemas import (
    AppType,
    CoolifyApplicationRequest,
    CoolifyApplicationResponse,
    CoolifyProjectInfo,
    CoolifyProjectsListResponse,
    DeploymentProvider,
    ProjectDeployResponse,
)


@dataclass
class CoolifyConfig:
    enabled: bool
    base_url: str
    api_token: str | None
    default_project_name: str
    default_environment_name: str


class CoolifyService:
    def __init__(self, config: CoolifyConfig, timeout: int = 20):
        self.config = config
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self.config.api_token:
            return {}
        return {"Authorization": f"Bearer {self.config.api_token}"}

    def list_projects(self) -> CoolifyProjectsListResponse:
        if not self.config.enabled:
            return CoolifyProjectsListResponse(projects=[], count=0)
        if not self.config.api_token:
            return CoolifyProjectsListResponse(projects=[], count=0)
        with httpx.Client(base_url=self.config.base_url, timeout=self.timeout) as client:
            resp = client.get("/api/v1/projects", headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()
        projects = [
            CoolifyProjectInfo(
                uuid=item.get("uuid"),
                name=item.get("name", "unknown"),
                environment_name=item.get("environment_name"),
                status=item.get("status"),
            )
            for item in payload
        ]
        return CoolifyProjectsListResponse(projects=projects, count=len(projects))

    def ensure_project(self, project_name: str | None = None) -> CoolifyProjectInfo | None:
        project_name = project_name or self.config.default_project_name
        if not self.config.enabled or not self.config.api_token:
            return None
        current = self.list_projects().projects
        for item in current:
            if item.name == project_name:
                return item
        with httpx.Client(base_url=self.config.base_url, timeout=self.timeout) as client:
            resp = client.post(
                "/api/v1/projects",
                headers=self._headers(),
                json={"name": project_name, "description": "Managed by hapi"},
            )
            resp.raise_for_status()
            payload = resp.json()
        return CoolifyProjectInfo(uuid=payload.get("uuid"), name=payload.get("name", project_name))

    def register_application(self, request: CoolifyApplicationRequest, project_repo_root: Path) -> CoolifyApplicationResponse:
        if not self.config.enabled:
            return CoolifyApplicationResponse(ok=False, error="coolify_disabled")
        if not self.config.api_token:
            return CoolifyApplicationResponse(ok=False, error="coolify_not_configured")

        project = self.ensure_project(request.project_name)
        if not project or not project.uuid:
            return CoolifyApplicationResponse(ok=False, error="coolify_project_unavailable")

        # Phase 2 keeps registration conservative: metadata is prepared for monorepo deployment.
        details = {
            "project_uuid": project.uuid,
            "environment_name": request.environment_name,
            "base_directory": request.base_directory,
            "domain": request.domain,
            "app_type": request.app_type.value,
            "repo_mode": "monorepo_subdirectory",
            "repo_root": project_repo_root.name,
        }
        return CoolifyApplicationResponse(ok=True, project=project, details=details)

    def deploy_project(self, request: CoolifyApplicationRequest, project_repo_root: Path) -> ProjectDeployResponse:
        registration = self.register_application(request, project_repo_root)
        if not registration.ok:
            return ProjectDeployResponse(
                slug=request.slug,
                provider=DeploymentProvider.coolify,
                deployed=False,
                status="error",
                error=registration.error,
                details=registration.details,
            )
        return ProjectDeployResponse(
            slug=request.slug,
            provider=DeploymentProvider.coolify,
            deployed=False,
            status="ready_for_coolify",
            details=registration.details,
        )
