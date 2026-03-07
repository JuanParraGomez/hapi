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
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
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

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def utcnow_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
