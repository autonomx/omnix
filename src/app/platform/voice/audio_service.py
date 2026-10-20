"""Client for Voice Studio's audio service (Phase 4): isolation, enhancement and watermarks.

The service (``src/services/audio/audio_server.py``) runs its models as exempt
helpers beside the TTS engine. ``OMNIX_AUDIO_URL`` names it; without it the
audio tools are unavailable and say so.

Errors come in two kinds: ``AudioToolRequestError`` when retrying cannot help
(a model that is not set up, audio that cannot be read) and
``AudioServiceUnavailable`` when it might (the service is down, or a model
does not fit in VRAM right now).
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

_REQUEST_CODES = {"model_missing", "invalid_request", "decode_failed", "empty_audio"}


class AudioServiceUnavailable(RuntimeError):
    """The audio service cannot do this now; a retry may succeed."""


class AudioToolRequestError(ValueError):
    """The audio service cannot do this as asked; retrying cannot help."""


def audio_service_url() -> str:
    from app.runtime.config import get_runtime_config

    endpoint = get_runtime_config().audio
    return endpoint.url.rstrip("/") if endpoint is not None else ""


@dataclass(frozen=True)
class Stems:
    vocals: bytes
    background: bytes
    sample_rate: int
    model: str


class AudioServiceClient:
    def __init__(self, base_url: str | None = None, http: Any = None) -> None:
        from app.runtime.http_client import shared_http_client

        self.base_url = (base_url if base_url is not None else audio_service_url()).rstrip("/")
        self.http = http or shared_http_client("audio-service")

    def _require_url(self) -> str:
        if not self.base_url:
            raise AudioServiceUnavailable(
                "The audio service is not configured (OMNIX_AUDIO_URL); set up the omnix-audio environment "
                "from src/services/audio/audio.lock.txt and start Omnix again")
        return self.base_url

    def health(self) -> dict[str, Any]:
        try:
            response = self.http.get(self._require_url() + "/health", timeout=5, retry=False)
            response.raise_for_status()
        except AudioServiceUnavailable:
            raise
        except Exception as exc:
            raise AudioServiceUnavailable(f"The audio service is not answering: {exc}") from exc
        return response.json()

    def _post(self, path: str, audio: bytes, filename: str, fields: dict[str, Any] | None = None,
              timeout: float = 900) -> dict[str, Any]:
        from app.security.service_token import service_headers

        try:
            response = self.http.post(
                self._require_url() + path,
                files={"file": (filename or "audio.wav", audio, "application/octet-stream")},
                data={key: str(value) for key, value in (fields or {}).items()},
                headers=service_headers(), timeout=timeout, retry=False,
            )
        except AudioServiceUnavailable:
            raise
        except Exception as exc:
            raise AudioServiceUnavailable(f"The audio service is not answering: {exc}") from exc
        # Outcomes to act on arrive as 200 envelopes ({"ok": false, "code", "message"}); the
        # service's middleware replaces error bodies with a bare {"error": <code>}.
        if response.status_code == 200:
            data = response.json()
            if data.get("ok") is not False:
                return data
            code, message = str(data.get("code") or ""), str(data.get("message") or "The audio tool failed")
            if code in _REQUEST_CODES:
                raise AudioToolRequestError(message)
            raise AudioServiceUnavailable(message)
        try:
            code = str(response.json().get("error") or "")
        except ValueError:
            code = ""
        message = f"The audio service refused the request ({code or response.status_code})"
        if response.status_code in {400, 404, 413, 422}:
            raise AudioToolRequestError(message)
        raise AudioServiceUnavailable(message)

    def isolate(self, audio: bytes, filename: str, *, model: str = "roformer") -> Stems:
        """Split speech from everything else: vocal and background stems (WAV)."""
        result = self._post("/audio/isolate", audio, filename, {"model": model})
        return Stems(vocals=base64.b64decode(result["vocals"]), background=base64.b64decode(result["background"]),
                     sample_rate=int(result["sample_rate"]), model=str(result["model"]))

    def enhance(self, audio: bytes, filename: str) -> tuple[bytes, dict[str, Any]]:
        """Denoised speech (WAV) and what was done."""
        result = self._post("/audio/enhance", audio, filename)
        return base64.b64decode(result["audio"]), {key: value for key, value in result.items() if key != "audio"}

    def watermark(self, wav: bytes, *, message: int) -> tuple[bytes, dict[str, Any]]:
        """The WAV with an inaudible AudioSeal watermark carrying a 16-bit ``message``."""
        result = self._post("/audio/watermark", wav, "render.wav", {"message": int(message)}, timeout=300)
        return base64.b64decode(result["audio"]), {key: value for key, value in result.items() if key != "audio"}

    def detect(self, audio: bytes, filename: str) -> dict[str, Any]:
        """Whether audio carries an AudioSeal watermark: probability, decoded message, verdict."""
        return self._post("/audio/watermark/detect", audio, filename, timeout=300)


__all__ = [
    "AudioServiceClient",
    "AudioServiceUnavailable",
    "AudioToolRequestError",
    "Stems",
    "audio_service_url",
]
