from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
import base64
import subprocess
import time

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
    verify_ssl: bool
    server_uuid: str | None
    destination_uuid: str | None
    default_git_branch: str
    git_private_key_uuid: str | None
    default_project_name: str
    default_environment_name: str


class CoolifyService:
    def __init__(self, config: CoolifyConfig, timeout: int = 20, deploy_poll_seconds: int = 120):
        self.config = config
        self.timeout = timeout
        self.deploy_poll_seconds = deploy_poll_seconds

    def _headers(self) -> dict[str, str]:
        if not self.config.api_token:
            return {}
        return {"Authorization": f"Bearer {self.config.api_token}"}

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.config.base_url,
            timeout=self.timeout,
            verify=self.config.verify_ssl,
        )

    def _request(self, method: str, path: str, **kwargs) -> dict | list:
        with self._client() as client:
            resp = client.request(method, path, headers=self._headers(), **kwargs)
            resp.raise_for_status()
            if not resp.content:
                return {}
            return resp.json()

    def list_projects(self) -> CoolifyProjectsListResponse:
        if not self.config.enabled:
            return CoolifyProjectsListResponse(projects=[], count=0)
        if not self.config.api_token:
            return CoolifyProjectsListResponse(projects=[], count=0)
        payload = self._request("GET", "/api/v1/projects")
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

    def health(self) -> dict[str, object]:
        if not self.config.enabled:
            return {
                "enabled": False,
                "configured": False,
                "reachable": False,
                "base_url": self.config.base_url,
                "reason": "coolify_disabled",
            }
        if not self.config.api_token:
            return {
                "enabled": True,
                "configured": False,
                "reachable": False,
                "base_url": self.config.base_url,
                "reason": "coolify_not_configured",
            }
        try:
            projects = self.list_projects()
            return {
                "enabled": True,
                "configured": True,
                "reachable": True,
                "base_url": self.config.base_url,
                "project_count": projects.count,
            }
        except Exception as exc:  # pragma: no cover - network variability
            return {
                "enabled": True,
                "configured": True,
                "reachable": False,
                "base_url": self.config.base_url,
                "reason": str(exc),
            }

    def resources(self) -> dict[str, object]:
        health = self.health()
        return {
            "health": health,
            "projects": self.list_projects().model_dump(mode="json") if health.get("reachable") else {"projects": [], "count": 0},
            "default_project_name": self.config.default_project_name,
            "default_environment_name": self.config.default_environment_name,
        }

    def list_applications(self) -> list[dict]:
        if not self.config.enabled or not self.config.api_token:
            return []
        payload = self._request("GET", "/api/v1/applications")
        return payload if isinstance(payload, list) else []

    def _normalize_public_repo_url(self, repo_url: str) -> str:
        if repo_url.startswith("git@github.com:"):
            repo_path = repo_url.removeprefix("git@github.com:")
            return f"https://github.com/{repo_path}"
        return repo_url

    def _resolve_git_dir(self, project_repo_root: Path) -> Path | None:
        dot_git = project_repo_root / ".git"
        if dot_git.is_dir():
            return dot_git
        if dot_git.is_file():
            try:
                raw = dot_git.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            prefix = "gitdir:"
            if not raw.lower().startswith(prefix):
                return None
            git_dir = raw[len(prefix):].strip()
            resolved = (project_repo_root / git_dir).resolve()
            return resolved if resolved.exists() else None
        return None

    def _detect_repo_url(self, project_repo_root: Path) -> str | None:
        git_dir = self._resolve_git_dir(project_repo_root)
        if git_dir:
            config_path = git_dir / "config"
            if config_path.exists():
                parser = configparser.ConfigParser()
                try:
                    parser.read(config_path, encoding="utf-8")
                except (configparser.Error, OSError):
                    parser = None
                if parser:
                    for section in ('remote "origin"', "remote 'origin'"):
                        if parser.has_section(section):
                            repo_url = parser.get(section, "url", fallback="").strip()
                            if repo_url:
                                return repo_url
        try:
            proc = subprocess.run(
                ["git", "-C", str(project_repo_root), "remote", "get-url", "origin"],
                check=True,
                capture_output=True,
                text=True,
            )
        except Exception:
            return None
        repo_url = proc.stdout.strip()
        return repo_url or None

    def _resolve_server_uuid(self, applications: list[dict]) -> str | None:
        if self.config.server_uuid:
            return self.config.server_uuid
        for item in applications:
            destination = item.get("destination") or {}
            server = destination.get("server") or {}
            if server.get("uuid"):
                return server["uuid"]
        return None

    def _resolve_destination_uuid(self, applications: list[dict]) -> str | None:
        if self.config.destination_uuid:
            return self.config.destination_uuid
        for item in applications:
            destination = item.get("destination") or {}
            if destination.get("uuid"):
                return destination["uuid"]
        return None

    def _find_existing_application(self, request: CoolifyApplicationRequest, applications: list[dict]) -> dict | None:
        for item in applications:
            if item.get("uuid") == request.slug or item.get("name") == request.slug:
                return item
            if item.get("base_directory") == request.base_directory:
                return item
            fqdn = item.get("fqdn") or ""
            if request.domain and request.domain in fqdn:
                return item
        return None

    def _status_from_application(self, application: dict) -> tuple[bool, str]:
        raw = str(application.get("status") or "").lower()
        if "unhealthy" in raw or "exited" in raw or "error" in raw or "failed" in raw:
            return False, "failed"
        if "healthy" in raw or raw.startswith("running"):
            return True, "deployed"
        if "starting" in raw or "queued" in raw or "building" in raw or "created" in raw:
            return False, "deploying"
        return False, "deploying"

    def _wait_for_application(self, application_uuid: str) -> dict:
        deadline = time.time() + self.deploy_poll_seconds
        latest = self._request("GET", f"/api/v1/applications/{application_uuid}")
        while time.time() < deadline:
            deployed, status = self._status_from_application(latest)
            if deployed or status == "failed":
                return latest
            time.sleep(3)
            latest = self._request("GET", f"/api/v1/applications/{application_uuid}")
        return latest

    def _build_create_payload(self, request: CoolifyApplicationRequest, project_uuid: str, server_uuid: str, destination_uuid: str, repo_url: str, build_pack: str, dockerfile_location: str | None) -> dict:
        custom_labels = self._build_public_proxy_labels(request)
        payload = {
            "project_uuid": project_uuid,
            "server_uuid": server_uuid,
            "environment_name": request.environment_name,
            "destination_uuid": destination_uuid,
            "name": request.slug,
            "description": f"Managed by hapi for {request.slug}",
            "git_repository": repo_url,
            "git_branch": self.config.default_git_branch,
            "build_pack": build_pack,
            "ports_exposes": str(request.port or 80),
            "domains": f"https://{request.domain}" if request.domain else "",
            "base_directory": request.base_directory,
            "is_auto_deploy_enabled": True,
            "is_force_https_enabled": True,
            "autogenerate_domain": False,
            "instant_deploy": True,
            "health_check_enabled": True,
            "health_check_path": "/",
            "health_check_port": str(request.port or 80),
            "custom_labels": custom_labels,
            "force_domain_override": True,
        }
        if build_pack == "dockerfile" and dockerfile_location:
            payload["dockerfile_location"] = dockerfile_location
        if build_pack == "static":
            payload["is_static"] = True
            payload["static_image"] = "nginx:alpine"
        if self.config.git_private_key_uuid:
            payload["private_key_uuid"] = self.config.git_private_key_uuid
        return payload

    def _build_public_proxy_labels(self, request: CoolifyApplicationRequest) -> str:
        if not request.domain:
            return ""
        router_slug = request.slug.replace(".", "-")
        service_name = f"svc-{router_slug}"
        port = str(request.port or 80)
        labels = [
            "traefik.enable=true",
            "traefik.docker.network=coolify",
            "traefik.http.middlewares.gzip.compress=true",
            "traefik.http.middlewares.redirect-to-https.redirectscheme.scheme=https",
            f"traefik.http.routers.web-{router_slug}.entryPoints=web",
            f"traefik.http.routers.web-{router_slug}.rule=Host(`{request.domain}`) && PathPrefix(`/`)",
            f"traefik.http.routers.web-{router_slug}.middlewares=redirect-to-https",
            f"traefik.http.routers.web-{router_slug}.service={service_name}",
            f"traefik.http.routers.websecure-{router_slug}.entryPoints=websecure",
            f"traefik.http.routers.websecure-{router_slug}.rule=Host(`{request.domain}`) && PathPrefix(`/`)",
            f"traefik.http.routers.websecure-{router_slug}.middlewares=gzip",
            f"traefik.http.routers.websecure-{router_slug}.service={service_name}",
            f"traefik.http.routers.websecure-{router_slug}.tls=true",
            f"traefik.http.routers.websecure-{router_slug}.tls.certresolver=myresolver",
            f"traefik.http.services.{service_name}.loadbalancer.server.port={port}",
        ]
        rendered = "\n".join(labels)
        return base64.b64encode(rendered.encode("utf-8")).decode("ascii")

    def _build_update_payload(
        self,
        request: CoolifyApplicationRequest,
    ) -> dict:
        return {
            "domains": f"https://{request.domain}" if request.domain else "",
            "is_force_https_enabled": True,
            "custom_labels": self._build_public_proxy_labels(request),
        }

    def ensure_project(self, project_name: str | None = None) -> CoolifyProjectInfo | None:
        project_name = project_name or self.config.default_project_name
        if not self.config.enabled or not self.config.api_token:
            return None
        current = self.list_projects().projects
        for item in current:
            if item.name == project_name:
                return item
        payload = self._request("POST", "/api/v1/projects", json={"name": project_name, "description": "Managed by hapi"})
        return CoolifyProjectInfo(uuid=payload.get("uuid"), name=payload.get("name", project_name))

    def register_application(self, request: CoolifyApplicationRequest, project_repo_root: Path) -> CoolifyApplicationResponse:
        if not self.config.enabled:
            return CoolifyApplicationResponse(ok=False, error="coolify_disabled")
        if not self.config.api_token:
            return CoolifyApplicationResponse(ok=False, error="coolify_not_configured")

        project = self.ensure_project(request.project_name)
        if not project or not project.uuid:
            return CoolifyApplicationResponse(ok=False, error="coolify_project_unavailable")

        applications = self.list_applications()
        server_uuid = self._resolve_server_uuid(applications)
        destination_uuid = self._resolve_destination_uuid(applications)
        if not server_uuid or not destination_uuid:
            return CoolifyApplicationResponse(ok=False, error="coolify_destination_unavailable")

        existing = self._find_existing_application(request, applications)
        details = {
            "project_uuid": project.uuid,
            "server_uuid": server_uuid,
            "destination_uuid": destination_uuid,
            "environment_name": request.environment_name,
            "base_directory": request.base_directory,
            "domain": request.domain,
            "app_type": request.app_type.value,
            "repo_mode": "monorepo_subdirectory",
            "repo_root": project_repo_root.name,
        }
        if existing:
            repo_url = self._detect_repo_url(project_repo_root)
            if not repo_url:
                return CoolifyApplicationResponse(ok=False, error="git_remote_unavailable", details=details)
            project_path = project_repo_root / request.base_directory.lstrip("/")
            build_pack = "nixpacks"
            if (project_path / "Dockerfile").exists():
                build_pack = "dockerfile"
            elif request.app_type == AppType.static_html:
                build_pack = "static"
            update_payload = self._build_update_payload(request=request)
            try:
                self._request("PATCH", f"/api/v1/applications/{existing.get('uuid')}", json=update_payload)
            except httpx.HTTPStatusError as exc:
                error = exc.response.text.strip() or str(exc)
                return CoolifyApplicationResponse(
                    ok=False,
                    error="coolify_application_update_failed",
                    details={**details, "response": error, "application_uuid": existing.get("uuid")},
                )
            details["existing_application"] = True
            details["build_pack"] = build_pack
            details["application_status"] = existing.get("status")
            return CoolifyApplicationResponse(
                ok=True,
                project=project,
                application_uuid=existing.get("uuid"),
                details=details,
            )

        repo_url = self._detect_repo_url(project_repo_root)
        if not repo_url:
            return CoolifyApplicationResponse(ok=False, error="git_remote_unavailable", details=details)

        dockerfile_location = None
        project_path = project_repo_root / request.base_directory.lstrip("/")
        build_pack = "nixpacks"
        if (project_path / "Dockerfile").exists():
            build_pack = "dockerfile"
            dockerfile_location = "/Dockerfile"
        elif request.app_type == AppType.static_html:
            build_pack = "static"

        payload = self._build_create_payload(
            request=request,
            project_uuid=project.uuid,
            server_uuid=server_uuid,
            destination_uuid=destination_uuid,
            repo_url=self._normalize_public_repo_url(repo_url) if not self.config.git_private_key_uuid else repo_url,
            build_pack=build_pack,
            dockerfile_location=dockerfile_location,
        )
        path = "/api/v1/applications/private-deploy-key" if self.config.git_private_key_uuid else "/api/v1/applications/public"
        try:
            created = self._request("POST", path, json=payload)
        except httpx.HTTPStatusError as exc:
            error = exc.response.text.strip() or str(exc)
            return CoolifyApplicationResponse(ok=False, error="coolify_application_create_failed", details={**details, "response": error})
        details["build_pack"] = build_pack
        details["created_application"] = True
        return CoolifyApplicationResponse(
            ok=True,
            project=project,
            application_uuid=created.get("uuid"),
            details=details,
        )

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
        application_uuid = registration.application_uuid
        if not application_uuid:
            return ProjectDeployResponse(
                slug=request.slug,
                provider=DeploymentProvider.coolify,
                deployed=False,
                status="error",
                error="coolify_application_uuid_missing",
                details=registration.details,
            )
        details = dict(registration.details)
        details["application_uuid"] = application_uuid
        try:
            self._request("POST", f"/api/v1/applications/{application_uuid}/start")
        except httpx.HTTPStatusError as exc:
            details["start_error"] = exc.response.text.strip() or str(exc)
            return ProjectDeployResponse(
                slug=request.slug,
                provider=DeploymentProvider.coolify,
                deployed=False,
                status="error",
                error="coolify_start_failed",
                details=details,
            )
        application = self._wait_for_application(application_uuid)
        deployed, status = self._status_from_application(application)
        details["application_status"] = application.get("status")
        details["fqdn"] = application.get("fqdn")
        details["git_repository"] = application.get("git_repository")
        return ProjectDeployResponse(
            slug=request.slug,
            provider=DeploymentProvider.coolify,
            deployed=deployed,
            status=status,
            details=details,
        )

    def delete_application(self, *, slug: str, base_directory: str | None = None, domain: str | None = None) -> dict[str, object]:
        if not self.config.enabled:
            return {"deleted": False, "reason": "coolify_disabled"}
        if not self.config.api_token:
            return {"deleted": False, "reason": "coolify_not_configured"}
        apps = self.list_applications()
        target = None
        normalized_base = (base_directory or "").strip()
        for item in apps:
            fqdn = str(item.get("fqdn") or "")
            if str(item.get("name") or "") == slug or str(item.get("uuid") or "") == slug:
                target = item
                break
            if normalized_base and str(item.get("base_directory") or "") == normalized_base:
                target = item
                break
            if domain and domain in fqdn:
                target = item
                break
        if target is None:
            return {"deleted": False, "reason": "coolify_application_not_found"}
        app_uuid = target.get("uuid")
        if not app_uuid:
            return {"deleted": False, "reason": "coolify_application_uuid_missing"}
        try:
            self._request("DELETE", f"/api/v1/applications/{app_uuid}")
        except Exception as exc:  # pragma: no cover - network path
            return {"deleted": False, "reason": "coolify_application_delete_failed", "error": str(exc), "application_uuid": app_uuid}
        return {"deleted": True, "application_uuid": app_uuid}
