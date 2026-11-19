"""The person's voiceprint: the speaker embedding a live call compares each segment with (companion 2.1).

Stored per account in the database (owner decision Q2, 2026-11-15): module ``live-voice``, record type
``voiceprint``, record id the user id. The document store is keyed by workspace, so the user id is what makes it
per account. It holds the averaged embedding, the model, when it was made and from how many passages. No audio is
kept, the embedding is never logged and never goes back to the browser, and guests cannot enrol. Omnix has no
account deletion to hook into, so ``DELETE`` is how a print is removed.

    GET    /api/stt/voiceprint   whether this account has a print (never the print itself)
    POST   /api/stt/voiceprint   enrol or re-enrol from 2 to 5 read passages (16 kHz mono 16-bit WAV, 3-20 s each)
    DELETE /api/stt/voiceprint   remove it

The speech service embeds each passage (TitaNet, ``/speaker/embedding``); the passages must sound like one voice.
"""
from __future__ import annotations

import io
import logging
import math
import wave
from datetime import UTC, datetime

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, field_validator

from app.persistence.document_schemas import register_document_schema
from app.persistence.document_store import PostgresDocumentStore
from app.runtime.tenant_context import current_tenant

logger = logging.getLogger(__name__)

MODULE = "live-voice"
RECORD_TYPE = "voiceprint"
SPEAKER_MODEL = "titanet-large"
SAMPLE_RATE = 16_000
MIN_PASSAGES, MAX_PASSAGES = 2, 5
MIN_PASSAGE_SECONDS, MAX_PASSAGE_SECONDS = 3.0, 20.0
# A passage quieter than this is a muted or wrong microphone, not speech.
MIN_PASSAGE_RMS = 0.004
# Passages read by one person score well above this against each other; a passage under it is another voice,
# the TV or mostly noise, and the print would be a blend.
MIN_PASSAGE_AGREEMENT = 0.4
_EMBEDDING_TIMEOUT_SECONDS = 60.0  # the first embedding loads the model
_MAX_PASSAGE_BYTES = int(MAX_PASSAGE_SECONDS * SAMPLE_RATE * 2) + 4096


class VoiceprintDocument(BaseModel):
    embedding: list[float] = Field(min_length=64, max_length=1024)
    model: str = Field(min_length=1, max_length=64)
    created_at: str = Field(min_length=10, max_length=40)
    samples: int = Field(ge=1, le=MAX_PASSAGES)
    agreement: float = Field(ge=-1.0, le=1.0)

    @field_validator("embedding")
    @classmethod
    def _finite(cls, value: list[float]) -> list[float]:
        if not all(math.isfinite(item) for item in value):
            raise ValueError("embedding values must be finite")
        return value


register_document_schema(MODULE, RECORD_TYPE, VoiceprintDocument)


class VoiceprintStatus(BaseModel):
    enrolled: bool
    can_enrol: bool
    created_at: str | None = None
    samples: int = 0
    model: str | None = None


class VoiceprintError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _store() -> PostgresDocumentStore:
    return PostgresDocumentStore()


def _is_guest() -> bool:
    return current_tenant().has_role("guest")


def read_voiceprint(user_id: str | None = None) -> VoiceprintDocument | None:
    """This account's print, or None. A guest never has one."""
    if _is_guest():
        return None
    payload = _store().read(module=MODULE, record_type=RECORD_TYPE,
                            record_id=user_id or current_tenant().user_id, default=None)
    return VoiceprintDocument.model_validate(payload) if payload else None


def voiceprint_status() -> VoiceprintStatus:
    stored = read_voiceprint()
    return VoiceprintStatus(enrolled=stored is not None, can_enrol=not _is_guest(),
                            created_at=stored.created_at if stored else None,
                            samples=stored.samples if stored else 0, model=stored.model if stored else None)


def delete_voiceprint() -> VoiceprintStatus:
    _store().delete(module=MODULE, record_type=RECORD_TYPE, record_id=current_tenant().user_id)
    return voiceprint_status()


def passage_pcm(payload: bytes) -> bytes:
    """A passage's PCM16 samples, refusing anything but a 16 kHz mono 16-bit WAV of 3-20 s with speech in it."""
    try:
        with wave.open(io.BytesIO(payload), "rb") as source:
            if source.getnchannels() != 1 or source.getsampwidth() != 2 or source.getframerate() != SAMPLE_RATE:
                raise VoiceprintError(422, "invalid_audio", "Each passage must be 16 kHz mono 16-bit WAV")
            pcm = source.readframes(source.getnframes())
    except (EOFError, wave.Error) as exc:
        raise VoiceprintError(422, "invalid_audio", "A passage could not be read as WAV") from exc
    seconds = len(pcm) / 2 / SAMPLE_RATE
    if not MIN_PASSAGE_SECONDS <= seconds <= MAX_PASSAGE_SECONDS:
        raise VoiceprintError(422, "passage_length",
                              f"Each passage must be {MIN_PASSAGE_SECONDS:.0f} to {MAX_PASSAGE_SECONDS:.0f} seconds")
    import numpy as np

    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    if float(np.sqrt(np.mean(samples * samples))) < MIN_PASSAGE_RMS:
        raise VoiceprintError(422, "passage_silent", "A passage was silent; check the microphone")
    return pcm


def speaker_embedding(payload: bytes, filename: str, *, timeout: float = _EMBEDDING_TIMEOUT_SECONDS) -> list[float]:
    """A recording's speaker embedding from the speech service; raises ``VoiceprintError`` when it cannot give one."""
    from app.runtime.config import get_runtime_config
    from app.runtime.http_client import shared_http_client
    from app.security.service_token import service_headers

    endpoint = get_runtime_config().stt
    if endpoint is None:
        raise VoiceprintError(503, "speech_service_unavailable", "The speech service is not configured")
    try:
        response = shared_http_client("stt-service").post(
            endpoint.url.removesuffix("/transcribe") + "/speaker/embedding",
            files={"file": (filename, payload, "audio/wav")}, headers=service_headers(), timeout=timeout,
            retry=False)
        data = response.json() if response.status_code == 200 else {}
    except Exception as exc:  # noqa: BLE001 - any transport failure is "not now"
        raise VoiceprintError(503, "speech_service_unavailable", "The speech service did not answer") from exc
    embedding = data.get("embedding") if isinstance(data, dict) and data.get("ok") else None
    if not isinstance(embedding, list) or not embedding:
        message = str(data.get("message") or "") if isinstance(data, dict) else ""
        raise VoiceprintError(503, "speaker_model_unavailable", message or "The speaker model is not available")
    return [float(value) for value in embedding]


def _wav(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(SAMPLE_RATE)
        target.writeframes(pcm)
    return buffer.getvalue()


def build_voiceprint(passages: list[bytes], *, embed=None, now: datetime | None = None) -> VoiceprintDocument:
    """The averaged, unit-length embedding of the passages, refused when they do not sound like one voice."""
    import numpy as np

    embed = embed or speaker_embedding

    if not MIN_PASSAGES <= len(passages) <= MAX_PASSAGES:
        raise VoiceprintError(422, "passage_count", f"Read {MIN_PASSAGES} to {MAX_PASSAGES} passages")
    units = []
    for index, payload in enumerate(passages):
        vector = np.asarray(embed(_wav(passage_pcm(payload)), f"passage-{index + 1}.wav"), dtype=np.float64)
        norm = float(np.linalg.norm(vector))
        if not math.isfinite(norm) or norm <= 0:
            raise VoiceprintError(503, "speaker_model_unavailable", "The speaker model returned no embedding")
        units.append(vector / norm)
    if len({len(unit) for unit in units}) != 1:
        raise VoiceprintError(503, "speaker_model_unavailable", "The speaker model changed during enrolment")
    agreement = min(float(units[a] @ units[b]) for a in range(len(units)) for b in range(a + 1, len(units)))
    if agreement < MIN_PASSAGE_AGREEMENT:
        raise VoiceprintError(422, "voices_differ", "The passages did not sound like one voice; try again somewhere "
                                                    "quiet, with only you speaking")
    mean = np.mean(units, axis=0)
    mean = mean / float(np.linalg.norm(mean))
    return VoiceprintDocument(embedding=[round(float(value), 6) for value in mean], model=SPEAKER_MODEL,
                              created_at=(now or datetime.now(UTC)).isoformat(timespec="seconds"),
                              samples=len(units), agreement=round(agreement, 4))


def enrol_voiceprint(passages: list[bytes], *, embed=None) -> VoiceprintStatus:
    if _is_guest():
        raise VoiceprintError(403, "guest_cannot_enrol", "Sign up to teach Omnix your voice")
    document = build_voiceprint(passages, embed=embed)
    _store().write(document.model_dump(mode="json"), module=MODULE, record_type=RECORD_TYPE,
                   record_id=current_tenant().user_id)
    logger.info("voiceprint enrolled: %d passages, agreement %.3f", document.samples, document.agreement)
    return voiceprint_status()


def _http(error: VoiceprintError) -> HTTPException:
    return HTTPException(status_code=error.status, detail={"error": error.code, "message": error.message})


def register_voiceprint_routes(router: APIRouter) -> None:
    @router.get("/api/stt/voiceprint", response_model=VoiceprintStatus, tags=["speech"])
    def get_voiceprint() -> VoiceprintStatus:
        return voiceprint_status()

    @router.post("/api/stt/voiceprint", response_model=VoiceprintStatus, tags=["speech"])
    async def post_voiceprint(files: list[UploadFile] = File(...)) -> VoiceprintStatus:  # noqa: B008
        import asyncio

        if len(files) > MAX_PASSAGES:
            raise _http(VoiceprintError(422, "passage_count", f"Read {MIN_PASSAGES} to {MAX_PASSAGES} passages"))
        passages = []
        for upload in files:
            payload = await upload.read(_MAX_PASSAGE_BYTES + 1)
            if len(payload) > _MAX_PASSAGE_BYTES:
                raise _http(VoiceprintError(413, "passage_too_large", "A passage is too long"))
            passages.append(payload)
        try:
            return await asyncio.to_thread(enrol_voiceprint, passages)
        except VoiceprintError as error:
            raise _http(error) from None

    @router.delete("/api/stt/voiceprint", response_model=VoiceprintStatus, tags=["speech"])
    def remove_voiceprint() -> VoiceprintStatus:
        return delete_voiceprint()


__all__ = [
    "MODULE", "RECORD_TYPE", "SPEAKER_MODEL", "VoiceprintDocument", "VoiceprintError", "VoiceprintStatus",
    "build_voiceprint", "delete_voiceprint", "enrol_voiceprint", "passage_pcm", "read_voiceprint",
    "register_voiceprint_routes", "speaker_embedding", "voiceprint_status",
]
