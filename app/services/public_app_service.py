from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from app.models.schemas import (
    CoolifyHealthResponse,
    DeploymentStatus,
    PublicAppStatus,
    PublicAppDeploymentRequest,
    PublicAppRecord,
    PublicAppRegisterRequest,
    PublicAppsListResponse,
    PublicAppSyncRequest,
    PublicDeploymentRecord,
    PublicSummaryResponse,
    SyncEventRecord,
)
from app.services.coolify_service import CoolifyService
from app.storage.db import Database


class PublicAppService:
    def __init__(self, db: Database, coolify_service: CoolifyService) -> None:
        self.db = db
        self.coolify_service = coolify_service

    def list_apps(self) -> PublicAppsListResponse:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT * FROM public_apps ORDER BY updated_at DESC").fetchall()
        apps = [self._row_to_public_app(row) for row in rows]
        return PublicAppsListResponse(apps=apps, count=len(apps))

    def delete_by_project_slug(self, slug: str) -> dict[str, object]:
        with self.db.connect() as conn:
            rows = conn.execute("SELECT app_id FROM public_apps WHERE slug = ? OR project_slug = ?", (slug, slug)).fetchall()
            app_ids = [row["app_id"] for row in rows]
            for app_id in app_ids:
                conn.execute("DELETE FROM public_deployments WHERE app_id = ?", (app_id,))
                conn.execute("DELETE FROM sync_events WHERE app_id = ?", (app_id,))
            conn.execute("DELETE FROM public_apps WHERE slug = ? OR project_slug = ?", (slug, slug))
        return {"deleted": bool(app_ids), "count": len(app_ids), "app_ids": app_ids}

    def get_app(self, app_id: str) -> PublicAppRecord | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM public_apps WHERE app_id = ?", (app_id,)).fetchone()
        return self._row_to_public_app(row) if row else None

    def get_by_slug(self, slug: str) -> PublicAppRecord | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM public_apps WHERE slug = ?", (slug,)).fetchone()
        return self._row_to_public_app(row) if row else None

    def get_by_domain(self, domain: str) -> PublicAppRecord | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM public_apps WHERE domain = ?", (domain,)).fetchone()
        return self._row_to_public_app(row) if row else None

    def register(self, request: PublicAppRegisterRequest) -> PublicAppRecord:
        existing = None
        if request.app_id:
            existing = self.get_app(request.app_id)
        if existing is None:
            existing = self.get_by_slug(request.slug)
        if existing is None and request.domain:
            existing = self.get_by_domain(request.domain)

        now = datetime.now(timezone.utc)
        app_id = existing.app_id if existing else (request.app_id or f"app_{uuid.uuid4().hex[:12]}")
        created_at = existing.created_at if existing else now
        record = PublicAppRecord(
            app_id=app_id,
            slug=request.slug,
            name=request.name,
            app_type=request.app_type,
            framework=request.framework,
            repo_url=request.repo_url,
            branch=request.branch,
            commit_sha=request.commit_sha,
            public_url=request.public_url,
            domain=request.domain,
            deployment_provider=request.deployment_provider,
            data_strategy=request.data_strategy,
            project_slug=request.project_slug,
            status=request.status,
            tags=request.tags,
            metadata_json={**(existing.metadata_json if existing else {}), **request.metadata_json},
            created_at=created_at,
            updated_at=now,
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO public_apps (
                    app_id, slug, name, app_type, framework, repo_url, branch, commit_sha,
                    public_url, domain, deployment_provider, data_strategy_json, project_slug,
                    status, tags_json, metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.app_id,
                    record.slug,
                    record.name,
                    record.app_type.value,
                    record.framework,
                    record.repo_url,
                    record.branch,
                    record.commit_sha,
                    record.public_url,
                    record.domain,
                    record.deployment_provider.value,
                    json.dumps(record.data_strategy),
                    record.project_slug,
                    record.status.value,
                    json.dumps(record.tags),
                    json.dumps(record.metadata_json),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )
        if request.correlation_id:
            self.record_sync(app_id, PublicAppSyncRequest(target="registry", details={"action": "register"}, correlation_id=request.correlation_id))
        return record

    def record_deployment(self, app_id: str, request: PublicAppDeploymentRequest) -> PublicDeploymentRecord:
        app = self.get_app(app_id)
        if app is None:
            raise KeyError("public_app_not_found")
        now = datetime.now(timezone.utc)
        deployment = PublicDeploymentRecord(
            app_id=app_id,
            deployment_status=request.deployment_status,
            provider=request.provider,
            public_url=request.public_url or app.public_url,
            domain=request.domain or app.domain,
            commit_sha=request.commit_sha or app.commit_sha,
            details=request.details,
            updated_at=now,
        )
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO public_deployments (
                    app_id, deployment_status, provider, public_url, domain, commit_sha, details_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    deployment.app_id,
                    deployment.deployment_status.value,
                    deployment.provider.value,
                    deployment.public_url,
                    deployment.domain,
                    deployment.commit_sha,
                    json.dumps(deployment.details),
                    deployment.updated_at.isoformat(),
                ),
            )
        status = app.status
        if request.deployment_status == DeploymentStatus.deployed:
            status = PublicAppStatus.deployed
        elif request.deployment_status in {DeploymentStatus.ready_for_coolify, DeploymentStatus.deploying}:
            status = PublicAppStatus.ready_for_deploy
        elif request.deployment_status == DeploymentStatus.failed:
            status = PublicAppStatus.failed
        updated = app.model_copy(update={
            "public_url": deployment.public_url,
            "domain": deployment.domain,
            "commit_sha": deployment.commit_sha,
            "status": status,
            "updated_at": now,
        })
        self.register(
            PublicAppRegisterRequest(
                app_id=updated.app_id,
                slug=updated.slug,
                name=updated.name,
                app_type=updated.app_type,
                framework=updated.framework,
                repo_url=updated.repo_url,
                branch=updated.branch,
                commit_sha=updated.commit_sha,
                public_url=updated.public_url,
                domain=updated.domain,
                deployment_provider=updated.deployment_provider,
                data_strategy=updated.data_strategy,
                project_slug=updated.project_slug,
                status=updated.status,
                tags=updated.tags,
                metadata_json=updated.metadata_json,
                correlation_id=request.correlation_id,
            )
        )
        return deployment

    def deployment_status(self, app_id: str) -> PublicDeploymentRecord | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM public_deployments WHERE app_id = ?", (app_id,)).fetchone()
        if row is None:
            return None
        return PublicDeploymentRecord(
            app_id=row["app_id"],
            deployment_status=row["deployment_status"],
            provider=row["provider"],
            public_url=row["public_url"],
            domain=row["domain"],
            commit_sha=row["commit_sha"],
            details=json.loads(row["details_json"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def record_sync(self, app_id: str, request: PublicAppSyncRequest) -> SyncEventRecord:
        if self.get_app(app_id) is None:
            raise KeyError("public_app_not_found")
        record = SyncEventRecord(
            event_id=f"sync_{uuid.uuid4().hex[:12]}",
            app_id=app_id,
            target=request.target,
            status=request.status,
            details=request.details,
            correlation_id=request.correlation_id,
            created_at=datetime.now(timezone.utc),
        )
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO sync_events (event_id, app_id, target, status, details_json, correlation_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.event_id,
                    record.app_id,
                    record.target,
                    record.status.value,
                    json.dumps(record.details),
                    record.correlation_id,
                    record.created_at.isoformat(),
                ),
            )
        return record

    def coolify_health(self) -> CoolifyHealthResponse:
        details = self.coolify_service.health()
        return CoolifyHealthResponse(
            enabled=bool(details.get("enabled", False)),
            configured=bool(details.get("configured", False)),
            reachable=bool(details.get("reachable", False)),
            base_url=str(details.get("base_url", "")),
            details=details,
        )

    def public_summary(self) -> PublicSummaryResponse:
        apps = self.list_apps().apps
        return PublicSummaryResponse(
            total_apps=len(apps),
            deployed_apps=sum(1 for app in apps if app.status.value == "deployed"),
            failed_apps=sum(1 for app in apps if app.status.value == "failed"),
            latest_apps=apps[:5],
            coolify=self.coolify_health().model_dump(mode="json"),
        )

    @staticmethod
    def _row_to_public_app(row) -> PublicAppRecord:
        return PublicAppRecord(
            app_id=row["app_id"],
            slug=row["slug"],
            name=row["name"],
            app_type=row["app_type"],
            framework=row["framework"],
            repo_url=row["repo_url"],
            branch=row["branch"],
            commit_sha=row["commit_sha"],
            public_url=row["public_url"],
            domain=row["domain"],
            deployment_provider=row["deployment_provider"],
            data_strategy=json.loads(row["data_strategy_json"]),
            project_slug=row["project_slug"],
            status=row["status"],
            tags=json.loads(row["tags_json"]),
            metadata_json=json.loads(row["metadata_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
