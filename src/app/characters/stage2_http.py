"""HTTP transport for the Character Mode Stage 2 read-only pilot."""
from __future__ import annotations

import time
from typing import Any, Protocol

from .stage1_http import HttpStage1Gateway
from .stage2_contracts import duration_ms


class Stage2Gateway(Protocol):
    def health(self) -> dict[str, Any]: ...
    def list_sessions(self) -> dict[str, Any] | list[dict[str, Any]]: ...
    def list_characters(self) -> list[dict[str, Any]]: ...
    def create_character(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_session(self, session_id: str) -> dict[str, Any]: ...
    def set_interaction(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def delete_session(self, session_id: str) -> dict[str, Any]: ...
    def list_memory(self, session_id: str) -> dict[str, Any]: ...
    def list_candidates(self, session_id: str) -> dict[str, Any]: ...
    def create_memory(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def create_memory_status(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]: ...
    def delete_memory(self, memory_id: str, session_id: str, revision: int) -> dict[str, Any]: ...
    def memory_state(self, session_id: str) -> dict[str, Any]: ...
    def refresh_memory(self, session_id: str, revision: int | None, token_budget: int) -> dict[str, Any]: ...
    def stream_chat_diagnostics(self, session_id: str, payload: dict[str, Any]) -> tuple[float, int, dict[str, Any]]: ...


class HttpStage2Gateway(HttpStage1Gateway):
    def list_sessions(self) -> dict[str, Any]:
        return self._json("GET", "/api/chat/sessions")

    def delete_session(self, session_id: str) -> dict[str, Any]:
        return self._json("DELETE", f"/api/chat/sessions/{self._encoded(session_id)}")

    def create_memory(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json("POST", "/api/assistant/memory", payload=payload)

    def create_memory_status(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        response = self.session.post(
            self._url("/api/assistant/memory"),
            json=payload,
            timeout=self.timeout_seconds,
        )
        try:
            body = response.json()
        except ValueError:
            body = {"detail": response.text[:500]}
        return response.status_code, body if isinstance(body, dict) else {"detail": body}

    def delete_memory(
        self,
        memory_id: str,
        session_id: str,
        revision: int,
    ) -> dict[str, Any]:
        return self._json(
            "DELETE",
            f"/api/assistant/memory/{self._encoded(memory_id)}",
            params={"session_id": session_id, "expected_revision": revision},
        )

    def memory_state(self, session_id: str) -> dict[str, Any]:
        return self._json(
            "GET",
            f"/api/chat/sessions/{self._encoded(session_id)}/memory",
        )

    def refresh_memory(
        self,
        session_id: str,
        revision: int | None,
        token_budget: int,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"token_budget": token_budget}
        if revision is not None:
            payload["expected_snapshot_revision"] = revision
        return self._json(
            "POST",
            f"/api/chat/sessions/{self._encoded(session_id)}/memory/refresh",
            payload=payload,
        )

    def stream_chat_diagnostics(
        self,
        session_id: str,
        payload: dict[str, Any],
    ) -> tuple[float, int, dict[str, Any]]:
        started = time.perf_counter()
        first_token_ms: float | None = None
        response_character_count = 0
        complete_metadata: dict[str, Any] | None = None
        with self.session.post(
            self._url(
                f"/api/chat/sessions/{self._encoded(session_id)}/messages/stream"
            ),
            json=payload,
            timeout=self.timeout_seconds,
            stream=True,
        ) as response:
            if not response.ok:
                raise RuntimeError(
                    f"POST messages/stream returned HTTP {response.status_code}"
                )
            for event in self._sse_events(response):
                event_type = event.get("type")
                if event_type == "error":
                    raise RuntimeError(str(event.get("message") or "chat stream failed"))
                if event_type == "text_chunk" and isinstance(event.get("text"), str):
                    text = event["text"]
                    if text and first_token_ms is None:
                        first_token_ms = duration_ms(started)
                    response_character_count += len(text)
                if event_type == "complete":
                    metadata = event.get("metadata")
                    complete_metadata = metadata if isinstance(metadata, dict) else {}
        if first_token_ms is None:
            raise RuntimeError("chat stream completed without a text chunk")
        if complete_metadata is None:
            raise RuntimeError("chat stream completed without diagnostic metadata")
        return first_token_ms, response_character_count, complete_metadata


__all__ = ["HttpStage2Gateway", "Stage2Gateway"]
