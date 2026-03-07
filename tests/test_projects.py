from pathlib import Path

from app.models.schemas import ProjectCreateRequest, ProjectLifetime
from app.services.project_service import ProjectService
from app.storage.db import Database


def test_short_lived_project_gets_ttl(tmp_path: Path):
    db = Database(tmp_path / "hapi.db")
    db.init()
    service = ProjectService(db, default_ttl_hours=24)

    record = service.create(ProjectCreateRequest(name="tmp", lifetime=ProjectLifetime.short_lived))

    assert record.ttl_hours == 24
    assert record.expires_at is not None


def test_long_lived_project_has_no_expiry(tmp_path: Path):
    db = Database(tmp_path / "hapi.db")
    db.init()
    service = ProjectService(db, default_ttl_hours=24)

    record = service.create(ProjectCreateRequest(name="core", lifetime=ProjectLifetime.long_lived))

    assert record.ttl_hours is None
    assert record.expires_at is None
