"""PostgreSQL-backed live-chat evaluation persistence."""
from __future__ import annotations

from pathlib import Path

from app.gateway.live_chat_evaluation_store import LiveChatEvaluationStore
from app.persistence.document_store import PostgresDocumentStore


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


