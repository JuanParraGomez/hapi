from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

from app.models.schemas import RagSyncManifest, RagSyncPolicy, RagSyncResponse, RagSyncStatus, ReadmeUpdateCheck


class RagSyncService:
    def __init__(self, repo_root: Path, rag_manifest_root: str, policy: RagSyncPolicy, base_url: str, enabled: bool):
        self.repo_root = repo_root
        self.manifest_dir = repo_root / rag_manifest_root
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self.policy = policy
        self.base_url = base_url.rstrip("/")
        self.enabled = enabled and policy.enabled

    def manifest_path(self, slug: str) -> Path:
        return self.manifest_dir / f"{slug}.yaml"

    def build_signature(self, source_paths: list[Path]) -> str:
        digest = hashlib.sha256()
        for path in source_paths:
            digest.update(str(path.relative_to(self.repo_root)).encode())
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def current_manifest(self, slug: str) -> RagSyncManifest | None:
        path = self.manifest_path(slug)
        if not path.exists():
            return None
        return RagSyncManifest.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    def save_manifest(self, manifest: RagSyncManifest) -> RagSyncManifest:
        self.manifest_path(manifest.slug).write_text(
            yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
        return manifest

    def check_refresh_needed(self, slug: str, source_paths: list[Path]) -> ReadmeUpdateCheck:
        tracked = [str(path.relative_to(self.repo_root)) for path in source_paths]
        current_signature = self.build_signature(source_paths)
        manifest = self.current_manifest(slug)
        if not self.enabled:
            return ReadmeUpdateCheck(slug=slug, needs_refresh=False, reason="rag_sync_disabled", tracked_files=tracked)
        if manifest is None:
            return ReadmeUpdateCheck(slug=slug, needs_refresh=True, reason="no_previous_sync", tracked_files=tracked)
        if manifest.signature != current_signature:
            return ReadmeUpdateCheck(slug=slug, needs_refresh=True, reason="conceptual_signature_changed", tracked_files=tracked)
        return ReadmeUpdateCheck(slug=slug, needs_refresh=False, reason="in_sync", tracked_files=tracked)

    def sync(self, slug: str, source_paths: list[Path], metadata: dict[str, str], force: bool = False, note: str | None = None) -> RagSyncResponse:
        tracked = [str(path.relative_to(self.repo_root)) for path in source_paths]
        current_signature = self.build_signature(source_paths)
        check = self.check_refresh_needed(slug, source_paths)
        if not self.enabled:
            manifest = RagSyncManifest(slug=slug, source_paths=tracked, rag_sync_status=RagSyncStatus.disabled, signature=current_signature, notes=note)
            self.save_manifest(manifest)
            return RagSyncResponse(slug=slug, synced=False, rag_sync_status=RagSyncStatus.disabled, signature=current_signature, source_paths=tracked)
        if not force and not check.needs_refresh:
            manifest = self.current_manifest(slug)
            return RagSyncResponse(
                slug=slug,
                synced=False,
                rag_sync_status=manifest.rag_sync_status if manifest else RagSyncStatus.in_sync,
                signature=current_signature,
                document_id=manifest.document_id if manifest else None,
                source_paths=tracked,
                details={"reason": check.reason},
            )

        content_chunks = []
        for path in source_paths:
            content_chunks.append(f"# {path.relative_to(self.repo_root)}\n\n{path.read_text(encoding='utf-8')}")
        payload = {
            "text": "\n\n".join(content_chunks),
            "tenant_id": self.policy.tenant_id,
            "title": f"{slug} project documentation",
            "metadata": metadata,
        }
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(f"{self.base_url}/upload-text", json=payload)
                resp.raise_for_status()
                result = resp.json()
            manifest = RagSyncManifest(
                slug=slug,
                source_paths=tracked,
                last_sync_at=datetime.now(timezone.utc),
                rag_sync_status=RagSyncStatus.in_sync,
                signature=current_signature,
                document_id=result.get("document_id"),
                notes=note,
            )
            self.save_manifest(manifest)
            return RagSyncResponse(
                slug=slug,
                synced=True,
                rag_sync_status=RagSyncStatus.in_sync,
                signature=current_signature,
                document_id=result.get("document_id"),
                source_paths=tracked,
                details=result,
            )
        except Exception as exc:  # pragma: no cover - network path handled in tests with fakes
            manifest = RagSyncManifest(
                slug=slug,
                source_paths=tracked,
                last_sync_at=datetime.now(timezone.utc),
                rag_sync_status=RagSyncStatus.error,
                signature=current_signature,
                notes=str(exc),
            )
            self.save_manifest(manifest)
            return RagSyncResponse(
                slug=slug,
                synced=False,
                rag_sync_status=RagSyncStatus.error,
                signature=current_signature,
                source_paths=tracked,
                error=str(exc),
            )
