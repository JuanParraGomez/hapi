from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout = 10000")
            conn.execute("PRAGMA synchronous = NORMAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS discovery_runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    summary_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS service_inventory (
                    run_id TEXT NOT NULL,
                    service_id TEXT NOT NULL,
                    service_name TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, service_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    slug TEXT,
                    name TEXT NOT NULL,
                    description TEXT,
                    lifetime TEXT NOT NULL,
                    ttl_hours INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    expires_at TEXT,
                    status TEXT,
                    project_root TEXT,
                    template TEXT,
                    deployment_provider TEXT,
                    domain TEXT,
                    rag_sync_enabled INTEGER,
                    promoted_from TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS public_apps (
                    app_id TEXT PRIMARY KEY,
                    slug TEXT NOT NULL,
                    name TEXT NOT NULL,
                    app_type TEXT NOT NULL,
                    framework TEXT,
                    repo_url TEXT,
                    branch TEXT,
                    commit_sha TEXT,
                    public_url TEXT,
                    domain TEXT,
                    deployment_provider TEXT NOT NULL,
                    data_strategy_json TEXT NOT NULL,
                    project_slug TEXT,
                    status TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS public_deployments (
                    app_id TEXT PRIMARY KEY,
                    deployment_status TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    public_url TEXT,
                    domain TEXT,
                    commit_sha TEXT,
                    details_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_events (
                    event_id TEXT PRIMARY KEY,
                    app_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    correlation_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "projects", "slug", "TEXT")
            self._ensure_column(conn, "projects", "updated_at", "TEXT")
            self._ensure_column(conn, "projects", "status", "TEXT")
            self._ensure_column(conn, "projects", "project_root", "TEXT")
            self._ensure_column(conn, "projects", "template", "TEXT")
            self._ensure_column(conn, "projects", "deployment_provider", "TEXT")
            self._ensure_column(conn, "projects", "domain", "TEXT")
            self._ensure_column(conn, "projects", "rag_sync_enabled", "INTEGER")
            self._ensure_column(conn, "projects", "promoted_from", "TEXT")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_slug ON projects(slug)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_public_apps_slug ON public_apps(slug)")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_public_apps_domain ON public_apps(domain)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sync_events_app_id ON sync_events(app_id)")

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def utcnow_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
