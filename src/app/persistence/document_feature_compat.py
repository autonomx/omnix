"""PostgreSQL document adapters for existing bounded feature stores."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.gateway.live_chat_evaluation_store import LiveChatEvaluationStore
from app.research.source_store import ResearchSourceStore

from .document_store import PostgresDocumentStore


class PostgresLiveChatEvaluationStore(LiveChatEvaluationStore):
    """Keep evaluation/policy validation logic while replacing JSON authority."""

    def __init__(self, path: Path | None = None) -> None:
        if path is not None:
            raise RuntimeError(
                "file-backed live-chat evaluation authority is retired; use the legacy importer"
            )
        self.path = Path("postgresql://live-chat-evaluations")
        self._lock = __import__("threading").RLock()
        self._documents = PostgresDocumentStore()

    def _read(self) -> dict:
        payload = self._documents.read(
            module="live-chat",
            record_type="evaluation-policy-store",
            default=None,
        )
        if not isinstance(payload, dict):
            return self._fresh_payload()
        payload = dict(payload)
        payload.setdefault("format_version", 2)
        payload.setdefault("evaluations", [])
        policies = payload.setdefault("presence_policies", {})
        self._ensure_default_policies(policies)
        return payload

    def _write(self, payload: dict) -> None:
        self._documents.write(
            payload,
            module="live-chat",
            record_type="evaluation-policy-store",
        )


class PostgresResearchSourceStore(ResearchSourceStore):
    """Keep citation/provenance logic while persisting metadata in PostgreSQL."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        clock: Callable[[], str] | None = None,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        if path is not None:
            raise RuntimeError(
                "file-backed research source authority is retired; use the legacy importer"
            )
        from app.research.source_store import _utcnow

        self.path = Path("postgresql://research-sources")
        self.clock = clock or _utcnow
        self.id_factory = id_factory or (lambda: __import__("uuid").uuid4().hex)
        self._lock = __import__("threading").Lock()
        self._documents = PostgresDocumentStore()

    def _load(self) -> dict[str, dict]:
        payload = self._documents.read(
            module="research",
            record_type="source-provenance-store",
            default=None,
        )
        if not isinstance(payload, dict):
            return {"sources": {}, "snapshots": {}, "manifests": {}}
        return {
            "sources": dict(payload.get("sources") or {}),
            "snapshots": dict(payload.get("snapshots") or {}),
            "manifests": dict(payload.get("manifests") or {}),
        }

    def _save(self, payload: dict[str, dict]) -> None:
        self._documents.write(
            payload,
            module="research",
            record_type="source-provenance-store",
        )

    def save_extraction(self, snapshot_id: str, page: Any):
        """Store extracted content as an asset reference, not a mutable side file."""

        from app.assets.models import AssetRecord, AssetType
        from app.persistence.asset_compat import PostgresSharedAssetStoreAdapter
        from app.research.contracts import ResearchSourceSnapshot

        with self._lock:
            payload = self._load()
            raw = payload["snapshots"].get(snapshot_id)
            if raw is None:
                raise KeyError(f"research snapshot not found: {snapshot_id}")
            source_path = self._temporary_extraction_file(snapshot_id, str(page.text))
            asset_id = f"asset:research-extract:{snapshot_id}"
            try:
                asset = PostgresSharedAssetStoreAdapter().upsert_asset(
                    AssetRecord(
                        id=asset_id,
                        module="research",
                        type=AssetType.TRANSCRIPT,
                        mime_type="text/plain",
                        storage_path=str(source_path),
                        metadata={
                            "snapshot_id": snapshot_id,
                            "extractor_version": page.extractor_version,
                            "content_hash": page.content_hash,
                        },
                    )
                )
            finally:
                source_path.unlink(missing_ok=True)
            snapshot = ResearchSourceSnapshot.model_validate(raw).model_copy(
                update={
                    "published_at": page.published_at or raw.get("published_at"),
                    "extractor_version": page.extractor_version,
                    "extraction_status": "completed",
                    "content_hash": page.content_hash,
                    "extracted_text_ref": asset.id,
                }
            )
            payload["snapshots"][snapshot_id] = snapshot.model_dump(mode="json")
            self._save(payload)
        return snapshot

    @staticmethod
    def _temporary_extraction_file(snapshot_id: str, content: str) -> Path:
        import tempfile

        safe = snapshot_id.replace(":", "_").replace("/", "_")
        root = Path(tempfile.mkdtemp(prefix="omnix-research-extract-"))
        path = root / f"{safe}.txt"
        path.write_text(content, encoding="utf-8")
        return path
