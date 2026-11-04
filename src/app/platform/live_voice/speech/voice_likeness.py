"""How like its voice's own clip a live take sounds, by the speech service's speaker model (TitaNet).

Now and then the engine renders a phrase in what is plainly someone else's voice. On real takes those score around 0
against the clip, as another person's voice does, while the right voice scores about 0.7. Anything that goes wrong
here only means no score: a phrase is never lost or held up for the sake of this check.
"""
from __future__ import annotations

import io
import logging
import wave
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT_SECONDS = 1.0


def service_embedding(payload: bytes, filename: str) -> list[float] | None:
    """A recording's speaker embedding from the speech service, or None when it cannot give one now."""
    from app.runtime.config import get_runtime_config
    from app.runtime.http_client import shared_http_client
    from app.security.service_token import service_headers

    endpoint = get_runtime_config().stt
    if endpoint is None:
        return None
    response = shared_http_client("stt-service").post(
        endpoint.url.removesuffix("/transcribe") + "/speaker/embedding",
        files={"file": (filename, payload, "application/octet-stream")},
        headers=service_headers(),
        timeout=_REQUEST_TIMEOUT_SECONDS,
        retry=False,
    )
    if response.status_code != 200:
        return None
    data = response.json()
    embedding = data.get("embedding") if data.get("ok") else None
    return embedding if isinstance(embedding, list) else None


def clone_clip(speaker: str) -> str | None:
    from app.providers.voice_references import clone_reference

    return clone_reference(speaker)[0]


def _wav(pcm: Iterable[bytes], sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        target.writeframes(b"".join(pcm))
    return buffer.getvalue()


def _unit(vector: list[float] | None) -> np.ndarray | None:
    if vector is None:
        return None
    # Loaded with the first take: the gateway starts without numpy.
    import numpy as np

    values = np.asarray(vector, dtype=np.float32)
    norm = float(np.linalg.norm(values))
    return values / norm if norm > 0 else None


class VoiceLikeness:
    """Scores one voice's takes for a call; its clip is embedded once, when first needed."""

    def __init__(
        self,
        speaker: str,
        *,
        embed: Callable[[bytes, str], list[float] | None] = service_embedding,
        reference: Callable[[str], str | None] = clone_clip,
    ) -> None:
        self.speaker = speaker
        self._embed = embed
        self._reference = reference
        self._clip: np.ndarray | None = None

    def _clip_embedding(self) -> np.ndarray | None:
        if self._clip is None:
            path = self._reference(self.speaker)
            if path:
                self._clip = _unit(self._embed(Path(path).read_bytes(), Path(path).name))
        return self._clip

    def score(self, pcm: Iterable[bytes], sample_rate: int) -> float | None:
        """Cosine similarity of the take to the voice's clip; None when there is no answer."""
        try:
            clip = self._clip_embedding()
            if clip is None:
                return None
            take = _unit(self._embed(_wav(pcm, sample_rate), "take.wav"))
            return None if take is None else round(float((take * clip).sum()), 4)
        except Exception:  # noqa: BLE001 - this check must never cost a phrase
            logger.debug("Voice likeness check failed", exc_info=True)
            return None
