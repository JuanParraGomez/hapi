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
                    name TEXT NOT NULL,
                    description TEXT,
                    lifetime TEXT NOT NULL,
                    ttl_hours INTEGER,
                    created_at TEXT NOT NULL,
                    expires_at TEXT
                )
                """
            )


def utcnow_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
