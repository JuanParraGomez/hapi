from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.schemas import ProjectCreateRequest, ProjectLifetime, ProjectRecord
from app.storage.db import Database


class ProjectService:
    def __init__(self, db: Database, default_ttl_hours: int):
        self.db = db
        self.default_ttl_hours = default_ttl_hours

    def create(self, request: ProjectCreateRequest) -> ProjectRecord:
        now = datetime.now(timezone.utc)
        project_id = f"prj_{uuid.uuid4().hex[:12]}"
        ttl_hours = request.ttl_hours
        if request.lifetime == ProjectLifetime.short_lived:
            ttl_hours = ttl_hours or self.default_ttl_hours
            expires_at = now + timedelta(hours=ttl_hours)
        else:
            expires_at = None

        record = ProjectRecord(
            project_id=project_id,
            name=request.name,
            description=request.description,
            lifetime=request.lifetime,
            ttl_hours=ttl_hours,
            created_at=now,
            expires_at=expires_at,
        )

        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (project_id, name, description, lifetime, ttl_hours, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.project_id,
                    record.name,
                    record.description,
                    record.lifetime.value,
                    record.ttl_hours,
                    record.created_at.isoformat(),
                    record.expires_at.isoformat() if record.expires_at else None,
                ),
            )
        return record

    def list(self) -> list[ProjectRecord]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT project_id, name, description, lifetime, ttl_hours, created_at, expires_at FROM projects ORDER BY created_at DESC"
            ).fetchall()
        result: list[ProjectRecord] = []
        for row in rows:
            result.append(
                ProjectRecord(
                    project_id=row["project_id"],
                    name=row["name"],
                    description=row["description"],
                    lifetime=ProjectLifetime(row["lifetime"]),
                    ttl_hours=row["ttl_hours"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
                )
            )
        return result
