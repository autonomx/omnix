"""HTTP transport for the live Stage 1 Character Mode rehearsal."""
from __future__ import annotations

import json
import time
from typing import Any, Protocol
from urllib.parse import quote

import requests

from .stage1_contracts import duration_ms


class Stage1Gateway(Protocol):
    def health(self) -> dict[str, Any]: ...
    def list_characters(self) -> list[dict[str, Any]]: ...
    def create_character(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def update_character(self, character_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_character(self, character_id: str) -> dict[str, Any]: ...
    def voice_governance(self, asset_id: str) -> dict[str, Any]: ...
    def update_voice_governance(self, asset_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get_session(self, session_id: str) -> dict[str, Any]: ...
    def set_interaction(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def live_call_runtime(self, session_id: str) -> dict[str, Any]: ...
    def list_memory(self, session_id: str) -> dict[str, Any]: ...
    def list_candidates(self, session_id: str) -> dict[str, Any]: ...
    def stream_chat(self, session_id: str, payload: dict[str, Any]) -> tuple[float, str]: ...
    def stream_tts(self, payload: dict[str, Any]) -> tuple[float, int]: ...


class HttpStage1Gateway:
    """Requests-based gateway client used by the deployment rehearsal CLI."""

    def __init__(self, base_url: str, timeout_seconds: float = 120) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    @staticmethod
    def _encoded(value: str) -> str:
        return quote(value, safe="")

    def _json(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self.session.request(
            method,
            self._url(path),
            json=payload,
            params=params,
            timeout=self.timeout_seconds,
        )
        if not response.ok:
            raise RuntimeError(f"{method} {path} returned HTTP {response.status_code}")
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"{method} {path} returned a non-object response")
        return data

    def health(self) -> dict[str, Any]:
        return self._json("GET", "/api/health")

    def list_characters(self) -> list[dict[str, Any]]:
        payload = self._json("GET", "/api/characters", params={"include_archived": "true"})
        values = payload.get("characters")
        return [item for item in values if isinstance(item, dict)] if isinstance(values, list) else []

    def create_character(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json("POST", "/api/characters", payload=payload)

    def update_character(self, character_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json(
            "PATCH",
            f"/api/characters/{self._encoded(character_id)}",
            payload=payload,
        )

    def get_character(self, character_id: str) -> dict[str, Any]:
        return self._json(
            "GET",
            f"/api/characters/{self._encoded(character_id)}",
            params={"include_archived": "true"},
        )

    def voice_governance(self, asset_id: str) -> dict[str, Any]:
        return self._json(
            "GET",
            f"/api/voice-profiles/{self._encoded(asset_id)}/governance",
        )

    def update_voice_governance(self, asset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json(
            "PATCH",
            f"/api/voice-profiles/{self._encoded(asset_id)}/governance",
            payload=payload,
        )

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json("POST", "/api/chat/sessions", payload=payload)

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._json("GET", f"/api/chat/sessions/{self._encoded(session_id)}")

    def set_interaction(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._json(
            "POST",
            f"/api/chat/sessions/{self._encoded(session_id)}/interaction",
            payload=payload,
        )

    def live_call_runtime(self, session_id: str) -> dict[str, Any]:
        return self._json(
            "GET",
            f"/api/chat/sessions/{self._encoded(session_id)}/live-call/runtime",
        )

    def list_memory(self, session_id: str) -> dict[str, Any]:
        return self._json(
            "GET",
            "/api/assistant/memory",
            params={"session_id": session_id, "limit": 500},
        )

    def list_candidates(self, session_id: str) -> dict[str, Any]:
        return self._json(
            "GET",
            "/api/assistant/memory/candidates/pending",
            params={"session_id": session_id, "limit": 500},
        )

    @staticmethod
    def _sse_events(response: requests.Response):
        data_lines: list[str] = []
        for raw in response.iter_lines(decode_unicode=True):
            line = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
            if line == "":
                if data_lines:
                    payload = "\n".join(data_lines)
                    data_lines = []
                    try:
                        value = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict):
                        yield value
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            try:
                value = json.loads("\n".join(data_lines))
            except json.JSONDecodeError:
                return
            if isinstance(value, dict):
                yield value

    def stream_chat(self, session_id: str, payload: dict[str, Any]) -> tuple[float, str]:
        started = time.perf_counter()
        first_token_ms: float | None = None
        response_text = ""
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
                    response_text += text
        if first_token_ms is None:
            raise RuntimeError("chat stream completed without a text chunk")
        return first_token_ms, response_text.strip()

    def stream_tts(self, payload: dict[str, Any]) -> tuple[float, int]:
        started = time.perf_counter()
        with self.session.post(
            self._url("/api/tts/stream/server-sent-events"),
            json=payload,
            timeout=self.timeout_seconds,
            stream=True,
        ) as response:
            if not response.ok:
                raise RuntimeError(
                    f"POST tts/stream/server-sent-events returned HTTP {response.status_code}"
                )
            for event in self._sse_events(response):
                if event.get("type") == "error":
                    raise RuntimeError(str(event.get("message") or "TTS stream failed"))
                if event.get("type") == "chunk" and isinstance(event.get("audio_b64"), str):
                    encoded = event["audio_b64"]
                    if encoded:
                        return duration_ms(started), max(0, len(encoded) * 3 // 4)
        raise RuntimeError("TTS stream completed without an audio chunk")


__all__ = ["HttpStage1Gateway", "Stage1Gateway"]
