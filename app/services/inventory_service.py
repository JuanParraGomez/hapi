from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from app.models.schemas import DiscoveryResponse, ServiceInventoryItem
from app.storage.db import Database


@dataclass
class InventoryRun:
    run_id: str
    payload: DiscoveryResponse


class InventoryService:
    def __init__(self, db: Database):
        self.db = db

    def store_run(self, payload: DiscoveryResponse) -> InventoryRun:
        run_id = f"disc_{uuid.uuid4().hex[:12]}"
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO discovery_runs (run_id, created_at, summary_json) VALUES (?, ?, ?)",
                (run_id, payload.summary.discovered_at.isoformat(), payload.summary.model_dump_json()),
            )
            for item in payload.services:
                conn.execute(
                    "INSERT INTO service_inventory (run_id, service_id, service_name, payload_json) VALUES (?, ?, ?, ?)",
                    (run_id, item.service_id, item.service_name, item.model_dump_json()),
                )
        return InventoryRun(run_id=run_id, payload=payload)

    def latest_services(self) -> list[ServiceInventoryItem]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT run_id FROM discovery_runs ORDER BY created_at DESC LIMIT 1").fetchone()
            if not row:
                return []
            run_id = row["run_id"]
            rows = conn.execute(
                "SELECT payload_json FROM service_inventory WHERE run_id = ? ORDER BY service_name ASC", (run_id,)
            ).fetchall()
        return [ServiceInventoryItem.model_validate(json.loads(r["payload_json"])) for r in rows]

    def service_by_id(self, service_id: str) -> ServiceInventoryItem | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM service_inventory
                WHERE service_id = ?
                ORDER BY rowid DESC
                LIMIT 1
                """,
                (service_id,),
            ).fetchone()
        if not row:
            return None
        return ServiceInventoryItem.model_validate(json.loads(row["payload_json"]))
