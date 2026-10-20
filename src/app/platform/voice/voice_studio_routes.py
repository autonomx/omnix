"""Voice Studio's routes: take waveforms, saved scripts and takes, and the speech model list.

Peaks of a stored take are computed here so the browser draws its own canvas
(no waveform library, and long takes never travel twice). Scripts and takes
are workspace-scoped rows (``scripts_repository``). Transcripts are read,
edited (each save is a new revision), exported as subtitles, and mined for a
speaker's clone sample. The model list and the
Hugging Face token are workspace-admin tools: installs download into the
shared models folder.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
_ROUTE_SENTINEL = "_omnix_voice_studio_routes_registered"
PEAKS_PATH = "/api/voice/assets/{asset_id}/peaks"
_MAX_PEAK_SOURCE_BYTES = 200 * 1024 * 1024


class VoicePeaksResponse(BaseModel):
    asset_id: str
    duration: float
    sample_rate: int
    # One value per bin: the loudest absolute sample in it, 0..1.
    peaks: list[float]


class VoiceTake(BaseModel):
    id: str
    line_id: str
    asset_id: str
    job_id: str
    engine: str
    text_hash: str
    duration: float
    pinned: bool
    created_at: str


class VoiceScriptLine(BaseModel):
    id: str
    position: int
    speaker: str
    text: str
    pause_before_ms: int | None = None
    delivery_instruction: str = ""
    voice_id: str = ""
    selected_take_id: str = ""
    takes: list[VoiceTake] = Field(default_factory=list)


class VoiceScriptSummary(BaseModel):
    id: str
    title: str
    text: str
    engine: str
    settings: dict[str, Any] = Field(default_factory=dict)
    revision: int
    created_at: str
    updated_at: str


class VoiceScript(VoiceScriptSummary):
    lines: list[VoiceScriptLine] = Field(default_factory=list)


class VoiceScriptListResponse(BaseModel):
    scripts: list[VoiceScriptSummary]


class VoiceCastEntry(BaseModel):
    voice_id: str = ""
    delivery_instruction: str = Field(default="", max_length=500)


class VoiceScriptWrite(BaseModel):
    title: str = Field(default="", max_length=200)
    text: str = Field(max_length=200_000)
    engine: str = Field(default="", max_length=64)
    settings: dict[str, Any] = Field(default_factory=dict)
    # Speaker name (any case) -> voice and delivery.
    casting: dict[str, VoiceCastEntry] = Field(default_factory=dict)
    expected_revision: int | None = None


class VoiceTakePin(BaseModel):
    pinned: bool


class SpeechModelStatus(BaseModel):
    id: str
    kind: str
    label: str
    repo_id: str
    revision: str
    licence: str
    licence_url: str
    size_gb: float
    vram_gb: float
    residency: str
    service: str
    commercial_use: bool
    gated: bool
    source: str
    output_terms: str
    capabilities: list[str]
    requires_acceptance: bool
    status: str
    installed_revision: str
    accepted_terms: bool
    disk_bytes: int
    # The model service's Python environment: present, or the command that sets it up.
    environment: dict[str, Any] = Field(default_factory=dict)


class SpeechModelListResponse(BaseModel):
    models: list[SpeechModelStatus]
    # Where the Hugging Face token comes from: environment, os_protected_store or missing.
    hub_token_source: str
    # The GPU the TTS service reports (device, total and free VRAM), and the VRAM budget planned for.
    hardware: dict[str, Any] = Field(default_factory=dict)
    vram_target_gb: float = 24.0


class HubTokenWrite(BaseModel):
    token: str = Field(default="", max_length=500)


class TranscriptResponse(BaseModel):
    asset_id: str
    title: str
    # Bumped by every saved edit; a save names the revision it started from.
    revision: int
    document: dict[str, Any]


class TranscriptWrite(BaseModel):
    document: dict[str, Any]
    expected_revision: int


class WatermarkSetting(BaseModel):
    enabled: bool


class AudioToolsStatus(BaseModel):
    # Whether OMNIX_AUDIO_URL names the service, whether it answers, and what it can do.
    configured: bool
    available: bool
    detail: str = ""
    tools: dict[str, Any] = Field(default_factory=dict)
    watermark: WatermarkSetting


class SpeakerSampleRequest(BaseModel):
    speaker: str = Field(min_length=1, max_length=120)


class SpeakerSampleSpan(BaseModel):
    start: float
    end: float


class SpeakerSample(BaseModel):
    """A speaker's cleanest 10-30 s, ready to clone: WAV audio and the words it holds."""
    speaker: str
    text: str
    duration: float
    sample_rate: int
    mime_type: str
    audio_base64: str
    spans: list[SpeakerSampleSpan]


_MAX_SAMPLE_SOURCE_BYTES = 500 * 1024 * 1024
_SAMPLE_PAD_SECONDS = 0.05
_SAMPLE_GAP_SECONDS = 0.25


def _decode_source(audio: bytes) -> tuple[Any, int]:
    """Mono float samples of a stored recording (WAV, FLAC, Ogg or MP3)."""
    import io

    import soundfile as sf

    samples, rate = sf.read(io.BytesIO(audio), dtype="float64", always_2d=True)
    return samples.mean(axis=1), int(rate)


_MAX_TRANSCRIPT_BYTES = 20 * 1024 * 1024
_EXPORT_FORMATS = ("srt", "vtt", "txt", "json")


def _transcript_asset(asset_id: str) -> tuple[Any, Any]:
    """The transcript asset and its ``TranscriptDocument``, or a 404."""
    import json

    from app.assets import AssetType, default_asset_store
    from app.assets.content import AssetContentUnavailable, read_asset_bytes

    from .transcripts import document_from_stored

    asset = default_asset_store().get_asset(asset_id)
    if asset is None or asset.type != AssetType.TRANSCRIPT:
        raise HTTPException(status_code=404, detail="transcript_not_found")
    try:
        raw = json.loads(read_asset_bytes(asset, max_bytes=_MAX_TRANSCRIPT_BYTES).decode("utf-8"))
    except AssetContentUnavailable as exc:
        raise HTTPException(status_code=404, detail="transcript_unavailable") from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=422, detail="transcript_unreadable") from exc
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="transcript_unreadable")
    parents = list(asset.parent_asset_ids or [])
    return asset, document_from_stored(raw, source_asset_id=parents[0] if parents else "")


def _transcript_response(asset: Any, document: Any) -> dict[str, Any]:
    return {"asset_id": asset.id, "title": str(asset.metadata.get("title") or asset.id),
            "revision": int(asset.metadata.get("revision") or 1), "document": document.model_dump(by_alias=True)}


def waveform_peaks(wav_bytes: bytes, bins: int) -> tuple[list[float], float, int]:
    """Peaks of WAV audio, or of any format soundfile reads (a transcript's source recording)."""
    import wave

    from .effects import read_mono

    try:
        samples, rate = read_mono(wav_bytes)
    except (wave.Error, EOFError):
        samples, rate = _decode_source(wav_bytes)
    duration = len(samples) / rate if rate else 0.0
    if not len(samples):
        return [0.0] * bins, duration, rate
    edges = np.linspace(0, len(samples), bins + 1).astype(int)
    peaks = [
        float(np.max(np.abs(samples[start:end]))) if end > start else 0.0
        for start, end in zip(edges[:-1], edges[1:])
    ]
    return [round(min(1.0, peak), 4) for peak in peaks], duration, rate


def _hardware() -> dict[str, Any]:
    """The GPU as the TTS service sees it; empty when the service does not answer."""
    from app.runtime.config import get_runtime_config
    from app.runtime.http_client import shared_http_client

    endpoint = get_runtime_config().tts
    if endpoint is None:
        return {}
    try:
        response = shared_http_client("tts-service").get(endpoint.url.rstrip("/") + "/health", timeout=3, retry=False)
        gpu = response.json().get("gpu") or {}
    except Exception:
        logger.debug("The TTS service did not report its GPU", exc_info=True)
        return {}
    return {key: gpu[key] for key in ("device", "vram_total_bytes", "vram_free_bytes") if key in gpu}


def _require_admin() -> None:
    """Workspace admins only: anyone else gets 403, not a server error."""
    from app.runtime.tenant_context import TenantAccessDenied, current_tenant

    try:
        current_tenant().require_role("owner", "admin")
    except TenantAccessDenied as exc:
        raise HTTPException(status_code=403, detail="workspace_admin_required") from exc


def _require_postgres() -> None:
    from app.persistence.runtime import uses_postgresql_runtime

    if not uses_postgresql_runtime():
        raise HTTPException(status_code=503, detail="saved_scripts_need_postgresql")


def _casting(write: VoiceScriptWrite) -> dict[str, dict[str, str]]:
    return {name.casefold(): entry.model_dump() for name, entry in write.casting.items()}


def register_voice_studio_routes(router: APIRouter, state: Any) -> None:
    if getattr(state, _ROUTE_SENTINEL, False):
        return
    setattr(state, _ROUTE_SENTINEL, True)

    @router.get(PEAKS_PATH, response_model=VoicePeaksResponse)
    def voice_asset_peaks(asset_id: str, bins: int = Query(default=480, ge=16, le=4096)) -> VoicePeaksResponse:
        """Peaks of a stored take or recording, for Voice Studio's waveforms."""
        from app.assets import default_asset_store
        from app.assets.content import AssetContentUnavailable, read_asset_bytes

        asset = default_asset_store().get_asset(asset_id)
        if asset is None or not str(asset.mime_type or "").startswith("audio/"):
            raise HTTPException(status_code=404, detail="wav_take_not_found")
        try:
            data = read_asset_bytes(asset, max_bytes=_MAX_PEAK_SOURCE_BYTES)
            peaks, duration, rate = waveform_peaks(data, bins)
        except AssetContentUnavailable as exc:
            raise HTTPException(status_code=404, detail="wav_take_unavailable") from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail="wav_take_unreadable") from exc
        return VoicePeaksResponse(asset_id=asset_id, duration=duration, sample_rate=rate, peaks=peaks)

    @router.get("/api/voice/scripts", response_model=VoiceScriptListResponse)
    def list_voice_scripts(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
        """Saved Voice Studio scripts, most recently edited first."""
        _require_postgres()
        from .scripts_repository import list_scripts

        return {"scripts": list_scripts(limit)}

    @router.post("/api/voice/scripts", response_model=VoiceScript, status_code=201)
    def create_voice_script(write: VoiceScriptWrite) -> dict[str, Any]:
        """Save a new script; its lines get stable ids."""
        _require_postgres()
        from .scripts_repository import save_script

        return save_script(title=write.title, text=write.text, engine=write.engine, settings=write.settings,
                           casting=_casting(write))

    @router.get("/api/voice/scripts/{script_id}", response_model=VoiceScript)
    def get_voice_script(script_id: str) -> dict[str, Any]:
        """One script with its lines and every take."""
        _require_postgres()
        from .scripts_repository import ScriptNotFound, get_script

        try:
            return get_script(script_id)
        except ScriptNotFound as exc:
            raise HTTPException(status_code=404, detail="script_not_found") from exc

    @router.put("/api/voice/scripts/{script_id}", response_model=VoiceScript)
    def update_voice_script(script_id: str, write: VoiceScriptWrite) -> dict[str, Any]:
        """Save edits; unchanged lines keep their id and takes. 409 when the script moved on."""
        _require_postgres()
        from .scripts_repository import ScriptNotFound, ScriptRevisionConflict, save_script

        try:
            return save_script(title=write.title, text=write.text, engine=write.engine, settings=write.settings,
                               casting=_casting(write), script_id=script_id,
                               expected_revision=write.expected_revision)
        except ScriptNotFound as exc:
            raise HTTPException(status_code=404, detail="script_not_found") from exc
        except ScriptRevisionConflict as exc:
            raise HTTPException(status_code=409, detail="script_revision_conflict") from exc

    @router.delete("/api/voice/scripts/{script_id}", status_code=204)
    def delete_voice_script(script_id: str) -> None:
        """Delete a script and its takes' rows; the take audio stays in the asset store."""
        _require_postgres()
        from .scripts_repository import delete_script

        if not delete_script(script_id):
            raise HTTPException(status_code=404, detail="script_not_found")

    @router.post("/api/voice/scripts/{script_id}/lines/{line_id}/takes/{take_id}/select", response_model=VoiceScript)
    def select_voice_take(script_id: str, line_id: str, take_id: str) -> dict[str, Any]:
        """Use this take for the line; restitch rebuilds the render from selected takes."""
        _require_postgres()
        from .scripts_repository import ScriptNotFound, get_script, select_take

        try:
            select_take(script_id=script_id, line_id=line_id, take_id=take_id)
        except ScriptNotFound as exc:
            raise HTTPException(status_code=404, detail="take_not_found") from exc
        return get_script(script_id)

    @router.post("/api/voice/takes/{take_id}/pin", status_code=204)
    def pin_voice_take(take_id: str, write: VoiceTakePin) -> None:
        """Pin a take so it stands out in the line's take list."""
        _require_postgres()
        from .scripts_repository import pin_take

        pin_take(take_id=take_id, pinned=write.pinned)

    @router.get("/api/voice/models", response_model=SpeechModelListResponse)
    def list_speech_models() -> dict[str, Any]:
        """Speech models Omnix can install: licence, size, VRAM and whether the weights are present."""
        from app.security.provider_secret_store import model_hub_token_source

        from .model_install import list_model_status

        return {"models": list_model_status(), "hub_token_source": model_hub_token_source(),
                "hardware": _hardware()}

    @router.put("/api/voice/models/hub-token", response_model=SpeechModelListResponse)
    def save_hub_token(write: HubTokenWrite) -> dict[str, Any]:
        """Store (or clear) the Hugging Face token in the protected store; workspace admins only."""
        from app.security.provider_secret_store import model_hub_token_source, save_model_hub_token

        from .model_install import list_model_status

        _require_admin()
        save_model_hub_token(write.token)
        return {"models": list_model_status(), "hub_token_source": model_hub_token_source()}


    @router.get("/api/voice/transcripts/{asset_id}", response_model=TranscriptResponse)
    def get_transcript(asset_id: str) -> dict[str, Any]:
        """A transcript as an ``omnix-transcript-v1`` document (untimed transcripts open as one speaker)."""
        asset, document = _transcript_asset(asset_id)
        return _transcript_response(asset, document)

    @router.put("/api/voice/transcripts/{asset_id}", response_model=TranscriptResponse)
    def save_transcript(asset_id: str, write: TranscriptWrite) -> dict[str, Any]:
        """Save an edited transcript as the asset's next revision (renamed speakers, fixed words, split segments)."""
        import json
        from datetime import datetime, timezone

        from pydantic import ValidationError

        from app.assets import default_asset_store
        from app.runtime.paths import resources_data_root

        from .transcripts import TranscriptDocument

        asset, current = _transcript_asset(asset_id)
        revision = int(asset.metadata.get("revision") or 1)
        if write.expected_revision != revision:
            raise HTTPException(status_code=409, detail="transcript_revision_conflict")
        try:
            edited = TranscriptDocument.model_validate(write.document)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="transcript_invalid") from exc
        # The source, engine and schema are facts about the recording, not editable text.
        document = edited.model_copy(update={
            "source_asset_id": current.source_asset_id, "engine": current.engine,
            "duration": current.duration, "schema_": current.schema_,
        }).normalized()
        output_dir = resources_data_root() / "voice_studio" / "transcripts"
        output_dir.mkdir(parents=True, exist_ok=True)
        safe = "".join(char if char.isalnum() or char in "-_." else "-" for char in asset.id)
        path = output_dir / f"{safe}-r{revision + 1}.json"
        path.write_text(json.dumps(document.model_dump(by_alias=True), indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        metadata = {**asset.metadata, "revision": revision + 1, "text": document.text[:2000],
                    "speakers": document.speakers, "schema": document.schema_,
                    "edited_at": datetime.now(timezone.utc).isoformat()}
        store = default_asset_store()
        replace = getattr(store, "replace_content", None)
        if replace is not None:
            # PostgreSQL: content is stored by key, so the new revision replaces it, checked against the revision read.
            saved = replace(asset.id, path, metadata=metadata, expected_revision=revision)
            if saved is None:
                raise HTTPException(status_code=409, detail="transcript_revision_conflict")
        else:
            saved = store.upsert_asset(asset.model_copy(update={
                "storage_path": str(path), "storage_key": None, "checksum_sha256": None, "metadata": metadata}))
        return _transcript_response(saved, document)

    @router.post("/api/voice/transcripts/{asset_id}/speaker-sample", response_model=SpeakerSample)
    def speaker_sample(asset_id: str, request: SpeakerSampleRequest) -> dict[str, Any]:
        """Cut a speaker's cleanest 10-30 s from the source recording, as a clone sample with its words."""
        import base64

        from app.assets import default_asset_store
        from app.assets.content import AssetContentUnavailable, read_asset_bytes

        from .effects import write_mono
        from .transcripts import speaker_sample_spans

        _asset, document = _transcript_asset(asset_id)
        if request.speaker not in document.speakers:
            raise HTTPException(status_code=404, detail="speaker_not_found")
        spans = speaker_sample_spans(document, request.speaker)
        if not spans:
            raise HTTPException(status_code=422, detail="speaker_sample_too_short")
        source = default_asset_store().get_asset(document.source_asset_id) if document.source_asset_id else None
        if source is None:
            raise HTTPException(status_code=404, detail="transcript_source_not_found")
        try:
            samples, rate = _decode_source(read_asset_bytes(source, max_bytes=_MAX_SAMPLE_SOURCE_BYTES))
        except AssetContentUnavailable as exc:
            raise HTTPException(status_code=404, detail="transcript_source_unavailable") from exc
        except Exception as exc:
            raise HTTPException(status_code=422, detail="transcript_source_unreadable") from exc
        gap = np.zeros(int(_SAMPLE_GAP_SECONDS * rate))
        pieces = []
        for segment in spans:
            start = max(0, int((segment.start - _SAMPLE_PAD_SECONDS) * rate))
            end = min(len(samples), int((segment.end + _SAMPLE_PAD_SECONDS) * rate))
            pieces.extend([samples[start:end], gap])
        audio = np.concatenate(pieces[:-1]) if pieces else np.zeros(0)
        return {
            "speaker": request.speaker,
            "text": " ".join(segment.text for segment in spans),
            "duration": round(len(audio) / rate, 3),
            "sample_rate": rate,
            "mime_type": "audio/wav",
            "audio_base64": base64.b64encode(write_mono(audio, rate)).decode("ascii"),
            "spans": [{"start": segment.start, "end": segment.end} for segment in spans],
        }

    @router.get("/api/voice/audio-tools", response_model=AudioToolsStatus)
    def audio_tools_status() -> dict[str, Any]:
        """The audio service: is it there, which tools work, and whether renders are watermarked."""
        from .audio_service import AudioServiceClient, AudioServiceUnavailable, audio_service_url
        from .watermarking import watermark_enabled

        status: dict[str, Any] = {"configured": bool(audio_service_url()), "available": False, "detail": "",
                                  "tools": {}, "watermark": {"enabled": watermark_enabled()}}
        try:
            health = AudioServiceClient().health()
        except AudioServiceUnavailable as exc:
            status["detail"] = str(exc)
            return status
        status.update(available=bool(health.get("ok")), tools=dict(health.get("tools") or {}))
        return status

    @router.put("/api/voice/watermark", response_model=WatermarkSetting)
    def save_watermark_setting(write: WatermarkSetting) -> dict[str, Any]:
        """Turn render watermarking on or off for the workspace; workspace admins only."""
        from .watermarking import set_watermark_enabled

        _require_admin()
        return {"enabled": set_watermark_enabled(write.enabled)}

    @router.get("/api/voice/transcripts/{asset_id}/export")
    def export_transcript_file(asset_id: str, format: str = Query(default="srt")) -> Response:  # noqa: A002
        """The transcript as SRT or WebVTT subtitles, plain text, or JSON."""
        from .transcripts import export_transcript

        if format not in _EXPORT_FORMATS:
            raise HTTPException(status_code=422, detail="unsupported_transcript_format")
        asset, document = _transcript_asset(asset_id)
        body, media_type = export_transcript(document, format)  # type: ignore[arg-type]
        stem = "".join(char if char.isalnum() or char in "-_" else "-"
                       for char in str(asset.metadata.get("title") or "transcript"))[:80].strip("-") or "transcript"
        return Response(content=body.encode("utf-8"), media_type=f"{media_type}; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.{format}"'})


__all__ = ["PEAKS_PATH", "VoicePeaksResponse", "register_voice_studio_routes", "waveform_peaks"]
