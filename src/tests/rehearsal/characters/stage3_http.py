"""HTTP transport for the Character Mode Stage 3 write-memory pilot."""
from __future__ import annotations

from typing import Any, Protocol

from .stage2_http import HttpStage2Gateway, Stage2Gateway


class Stage3Gateway(Stage2Gateway, Protocol):
    def update_memory(
        self,
        memory_id: str,
        session_id: str,
        revision: int,
        content: str,
    ) -> dict[str, Any]: ...
    def approve_candidate(
        self,
        candidate_id: str,
        session_id: str,
        *,
        pinned: bool = False,
    ) -> dict[str, Any]: ...
    def reject_candidate(
        self,
        candidate_id: str,
        session_id: str,
        *,
        pinned: bool = False,
    ) -> dict[str, Any]: ...
    def delete_candidate(
        self,
        candidate_id: str,
        session_id: str,
        *,
        expected_status: str,
    ) -> dict[str, Any]: ...
    def list_jobs(self, *, limit: int = 100, full: bool = True) -> list[dict[str, Any]]: ...


class HttpStage3Gateway(HttpStage2Gateway):
    def update_memory(
        self,
        memory_id: str,
        session_id: str,
        revision: int,
        content: str,
    ) -> dict[str, Any]:
        return self._json(
            "PATCH",
            f"/api/assistant/memory/{self._encoded(memory_id)}",
            payload={
                "session_id": session_id,
                "expected_revision": revision,
                "content": content,
            },
        )

    def approve_candidate(
        self,
        candidate_id: str,
        session_id: str,
        *,
        pinned: bool = False,
    ) -> dict[str, Any]:
        return self._json(
            "POST",
            f"/api/assistant/memory/candidates/{self._encoded(candidate_id)}/approve",
            payload={"session_id": session_id, "pinned": pinned},
        )

    def reject_candidate(
        self,
        candidate_id: str,
        session_id: str,
        *,
        pinned: bool = False,
    ) -> dict[str, Any]:
        return self._json(
            "POST",
            f"/api/assistant/memory/candidates/{self._encoded(candidate_id)}/reject",
            payload={"session_id": session_id, "pinned": pinned},
        )

    def delete_candidate(
        self,
        candidate_id: str,
        session_id: str,
        *,
        expected_status: str,
    ) -> dict[str, Any]:
        return self._json(
            "DELETE",
            f"/api/assistant/memory/candidates/{self._encoded(candidate_id)}",
            payload={"session_id": session_id, "expected_status": expected_status},
        )

    def list_jobs(self, *, limit: int = 100, full: bool = True) -> list[dict[str, Any]]:
        payload = self._json(
            "GET",
            "/api/jobs",
            params={"limit": limit, "full": "true" if full else "false"},
        )
        values = payload.get("jobs")
        return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []


__all__ = ["HttpStage3Gateway", "Stage3Gateway"]
