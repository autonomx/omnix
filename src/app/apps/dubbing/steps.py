"""The dubbing pipeline's steps (Voice Studio Phase 6): each is its own durable job.

ingest -> separate -> transcribe -> translate -> cast -> synthesize, then a
person reviews; ``dub.mux`` runs only when every line is approved. A step
submitted with ``chain`` submits the next one when it finishes (a follow-up job,
so a draining module still accepts it); any step can also be run again on its
own, or for chosen lines. Re-running a step never touches an approved line.

The steps reach Voice Studio only through ``app.platform.voice.contracts``.
They take what they write back as callbacks (``jobs.py`` owns the
transactions), so each step reads as the pipeline it is.
"""
from __future__ import annotations

import base64
import hashlib
import io
import subprocess
import tempfile
import uuid
import wave
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

STEPS = ("ingest", "separate", "transcribe", "translate", "cast", "synthesize", "mux")
# Steps that chain on by themselves; review sits between synthesize and mux.
CHAINED = {"ingest": "separate", "separate": "transcribe", "transcribe": "translate",
           "translate": "cast", "cast": "synthesize"}
MIX_RATE = 44_100
VIDEO_SUFFIXES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
                  ".mkv": "video/x-matroska", ".webm": "video/webm"}
MAX_VIDEO_BYTES = 4 * 1024 ** 3
# Cloning wants 10-30 s of a speaker; a dub settles for 4 s rather than no voice.
MIN_CLONE_SECONDS = 4.0


class DubRequestError(ValueError):
    """The step cannot run as asked (a missing source, an unapproved line); retrying cannot help."""


# --- audio helpers ------------------------------------------------------------------------------


def resample(samples: np.ndarray, source: int, target: int) -> np.ndarray:
    """Linear-interpolation resampling: enough for speech moving between 24, 44.1 and 48 kHz."""
    if source == target or not len(samples):
        return samples.astype(np.float32)
    length = max(1, int(round(len(samples) * target / source)))
    positions = np.linspace(0, len(samples) - 1, length)
    return np.interp(positions, np.arange(len(samples)), samples).astype(np.float32)


def decode_wav(data: bytes) -> tuple[np.ndarray, int]:
    """Mono float samples of any file soundfile reads."""
    import soundfile as sf

    samples, rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    return samples.mean(axis=1), int(rate)


def encode_wav(samples: np.ndarray, rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes((np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    return buffer.getvalue()


def source_key(speaker: str, start: float, text: str) -> str:
    """A line's identity: its speaker, its start (to 0.1 s) and its words."""
    raw = f"{speaker}|{round(float(start), 1):.1f}|{' '.join(text.split())}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def run_ffmpeg(arguments: list[str]) -> None:
    from app.runtime.ffmpeg import ffmpeg_binary

    result = subprocess.run([ffmpeg_binary("video dubbing"), "-hide_banner", "-loglevel", "error", "-y", *arguments],
                            capture_output=True, timeout=3600, check=False)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[-400:]
        raise RuntimeError(f"FFmpeg failed: {detail}")


def _safe(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_" else "-" for char in value)


def approved(segment: dict[str, Any]) -> bool:
    """A person approved these exact words and this exact take."""
    return (segment.get("approved_revision") is not None
            and segment["approved_revision"] == segment["translation_revision"]
            and segment.get("approved_take_asset_id") == segment["take_asset_id"]
            and bool(segment["take_asset_id"]))


def take_is_current(segment: dict[str, Any]) -> bool:
    return bool(segment["take_asset_id"]) and segment["take_revision"] == segment["translation_revision"]


# --- step context ---------------------------------------------------------------------------------


class StepRun:
    """What a step needs: the project, its lines, the job (for authority) and asset storage."""

    def __init__(self, job: Any, job_store: Any, project: dict[str, Any], segments: list[dict[str, Any]]) -> None:
        self.job = job
        self.job_store = job_store
        self.project = project
        self.segments = segments
        payload = job.input_payload or {}
        self.line_ids = {str(value) for value in payload.get("line_ids") or []}

    def asset_bytes(self, key: str, *, max_bytes: int = 2 * 1024 ** 3) -> bytes:
        asset_id = self.project["source_asset_id"] if key == "source" else (self.project.get("assets") or {}).get(key, "")
        if not asset_id:
            raise DubRequestError(f"the project has no {key} yet; run the earlier steps first")
        return self.bytes_of(asset_id, max_bytes=max_bytes)

    def bytes_of(self, asset_id: str, *, max_bytes: int = 2 * 1024 ** 3) -> bytes:
        from app.assets import default_asset_store
        from app.assets.content import read_asset_bytes

        asset = default_asset_store().get_asset(asset_id)
        if asset is None:
            raise DubRequestError(f"{asset_id} is gone; run the step that made it again")
        return read_asset_bytes(asset, max_bytes=max_bytes)

    def store(self, *, name: str, data: bytes, kind: str, mime: str, title: str, parents: list[str],
              metadata: dict[str, Any] | None = None) -> str:
        from app.assets import AssetRecord, AssetType, default_asset_store
        from app.jobs.inline_execution import require_execution_authority
        from app.runtime.paths import resources_data_root

        folder = resources_data_root() / "dubbing" / _safe(self.project["id"])
        folder.mkdir(parents=True, exist_ok=True)
        # Every write is a new asset: stored content never changes under an id (PostgreSQL keeps the first
        # blob), a re-run never overwrites what an approval was bound to, and SRT and VTT stay apart.
        token = uuid.uuid4().hex[:12]
        path = folder / f"{Path(name).stem}-{token}{Path(name).suffix}"
        require_execution_authority(self.job_store, self.job.id)
        path.write_bytes(data)
        asset_type = AssetType.AUDIO if mime.startswith("audio/") else AssetType.EXPORT
        asset = default_asset_store().upsert_asset(AssetRecord(
            id=f"dubbing:{_safe(self.project['id'])}:{_safe(Path(name).name)}:{token}",
            module="dubbing",
            type=asset_type,
            mime_type=mime,
            storage_path=str(path),
            metadata={"title": title, "kind": kind, "project_id": self.project["id"], **(metadata or {})},
            source_job_id=self.job.id,
            parent_asset_ids=[parent for parent in parents if parent],
            created_at=datetime.now(timezone.utc).isoformat(),
            compat={"contract": "dubbing_v1"},
        ))
        return asset.id


# --- the steps ------------------------------------------------------------------------------------


def ingest(run: StepRun) -> dict[str, Any]:
    """The source video's audio, as 44.1 kHz stereo WAV."""
    from app.assets import default_asset_store

    source = default_asset_store().get_asset(run.project["source_asset_id"])
    if source is None:
        raise DubRequestError("the source video is gone")
    suffix = Path(source.storage_path or str(source.metadata.get("file_name") or "video.mp4")).suffix.lower()
    if suffix not in VIDEO_SUFFIXES:
        raise DubRequestError("the source must be an MP4, MOV, MKV or WebM video")
    with tempfile.TemporaryDirectory(prefix="omnix-dub-") as work:
        video = Path(work) / f"source{suffix}"
        video.write_bytes(run.asset_bytes("source", max_bytes=MAX_VIDEO_BYTES))
        audio = Path(work) / "audio.wav"
        run_ffmpeg(["-i", str(video), "-vn", "-ac", "2", "-ar", str(MIX_RATE), "-c:a", "pcm_s16le", str(audio)])
        data = audio.read_bytes()
    samples, rate = decode_wav(data)
    asset_id = run.store(name="audio.wav", data=data, kind="dub_source_audio", mime="audio/wav",
                         title=f"{run.project['title']} (audio)", parents=[source.id])
    return {"assets": {"audio": asset_id}, "duration_seconds": round(len(samples) / rate, 3)}


def separate(run: StepRun) -> dict[str, Any]:
    """Vocal and background stems of the source audio (Phase 4 isolation)."""
    from app.platform.voice.contracts import AudioServiceClient

    audio_id = run.project["assets"].get("audio", "")
    stems = AudioServiceClient().isolate(run.asset_bytes("audio"), "audio.wav", model="roformer")
    vocals = run.store(name="vocals.wav", data=stems.vocals, kind="dub_vocals", mime="audio/wav",
                       title=f"{run.project['title']} (voices)", parents=[audio_id], metadata={"model": stems.model})
    background = run.store(name="background.wav", data=stems.background, kind="dub_background", mime="audio/wav",
                           title=f"{run.project['title']} (background)", parents=[audio_id],
                           metadata={"model": stems.model})
    return {"assets": {"vocals": vocals, "background": background}}


def transcribe(run: StepRun) -> dict[str, Any]:
    """A timed, speaker-labelled transcript of the voices, and the lines to dub."""
    from app.platform.voice.contracts import transcribe_timed_audio

    document = transcribe_timed_audio(run.asset_bytes("vocals"), "vocals.wav",
                                      language=run.project["source_language"], diarize=True,
                                      speakers=int(run.project.get("speakers") or 0))
    lines = [{"source_key": source_key(segment.speaker, segment.start, segment.text), "speaker": segment.speaker,
              "start_seconds": round(segment.start, 3), "end_seconds": round(max(segment.end, segment.start + 0.2), 3),
              "source_text": segment.text}
             for segment in document.segments if segment.text.strip()]
    transcript = run.store(name="transcript.json", data=document.model_dump_json(by_alias=True, indent=2).encode(),
                           kind="dub_transcript", mime="application/json",
                           title=f"{run.project['title']} (transcript)",
                           parents=[run.project["assets"].get("vocals", "")])
    return {"assets": {"transcript": transcript}, "lines": lines}


def needs_translation(run: StepRun, segment: dict[str, Any]) -> bool:
    """Lines asked for; otherwise lines with no translation yet. Approved and hand-edited lines stay."""
    if run.line_ids:
        return segment["id"] in run.line_ids
    return not segment["translation"] and not approved(segment)


def translate(run: StepRun, translator: Any) -> dict[str, Any]:
    """Translations for the lines that need one, in batches with their neighbours as context."""
    from .translate import BATCH_SIZE, CONTEXT_LINES, LineToTranslate

    order = run.segments
    todo = [index for index, segment in enumerate(order) if needs_translation(run, segment)]
    results: dict[str, str] = {}
    for start in range(0, len(todo), BATCH_SIZE):
        batch = todo[start:start + BATCH_SIZE]
        first, last = batch[0], batch[-1]
        lines = [LineToTranslate(order[index]["id"], order[index]["speaker"], order[index]["source_text"],
                                 order[index]["end_seconds"] - order[index]["start_seconds"]) for index in batch]
        before = [segment["source_text"] for segment in order[max(0, first - CONTEXT_LINES):first]]
        after = [segment["source_text"] for segment in order[last + 1:last + 1 + CONTEXT_LINES]]
        results.update(translator.translate(lines, before=before, after=after,
                                            source=run.project["source_language"],
                                            target=run.project["target_language"]))
    # Each line's revision as it was read: a person's edit made while the LLM ran is kept, not overwritten.
    revisions = {order[index]["id"]: int(order[index]["translation_revision"]) for index in todo}
    return {"translations": results, "translation_revisions": revisions, "requested_lines": bool(run.line_ids)}


def cast(run: StepRun, clone: Callable[..., str]) -> dict[str, Any]:
    """A library voice per source speaker: cloned from their own isolated speech unless one is chosen."""
    from app.platform.voice.contracts import TranscriptDocument, speaker_sample_spans

    casting = dict(run.project.get("casting") or {})
    speakers = sorted({segment["speaker"] for segment in run.segments})
    document = TranscriptDocument.model_validate({"segments": [
        {"start": segment["start_seconds"], "end": segment["end_seconds"], "speaker": segment["speaker"],
         "text": segment["source_text"], "words": []} for segment in run.segments]})
    vocals: tuple[np.ndarray, int] | None = None
    uncast = []
    for speaker in speakers:
        if casting.get(speaker):
            continue
        spans = speaker_sample_spans(document, speaker, min_seconds=MIN_CLONE_SECONDS)
        if not spans:
            uncast.append(speaker)  # too little clean speech: the review screen asks for a voice
            continue
        if vocals is None:
            vocals = decode_wav(run.asset_bytes("vocals"))
        samples, rate = vocals
        gap = np.zeros(int(0.25 * rate), dtype=np.float32)
        pieces: list[np.ndarray] = []
        for span in spans:
            pieces += [samples[int(span.start * rate):int(span.end * rate)], gap]
        sample = encode_wav(np.concatenate(pieces[:-1]), rate)
        # Clone ids come from the name and the voice library is the device's, so the project is in it:
        # two projects with the same title never overwrite each other's cast.
        casting[speaker] = clone(name=f"{run.project['title']} - {speaker} ({_safe(run.project['id'])[-8:]})", wav=sample,
                                 text=" ".join(span.text for span in spans), language=run.project["source_language"])
    return {"casting": casting, "uncast": uncast}


def needs_take(run: StepRun, segment: dict[str, Any]) -> bool:
    if run.line_ids:
        return segment["id"] in run.line_ids
    return bool(segment["translation"]) and not approved(segment) and not take_is_current(segment)


def synthesize(run: StepRun, *, provider: Any, engine: str, translator: Any,
               save_translation: Callable[[str, str, int], int | None],
               save_take: Callable[..., None]) -> dict[str, Any]:
    """Render each line that needs a take and fit it to its budget (fit.py): stretch, else shorten, else flag."""
    from app.platform.voice.contracts import time_stretch, watermark_render

    from .fit import DURATION_ENGINES, MAX_SHORTENINGS, plan_fit
    from .translate import LineToTranslate

    casting = run.project.get("casting") or {}
    target = run.project["target_language"]
    counts: dict[str, int] = {}
    for segment in run.segments:
        if not needs_take(run, segment):
            continue
        if not segment["translation"]:
            counts["untranslated"] = counts.get("untranslated", 0) + 1
            continue
        voice = segment["voice_override"] or casting.get(segment["speaker"]) or "default"
        budget = segment["end_seconds"] - segment["start_seconds"]
        text, revision, shortenings = segment["translation"], segment["translation_revision"], 0
        # A person's words are theirs: never shortened, only flagged when they run over.
        person = segment.get("translation_origin") == "person"
        moved_on = False
        while True:
            options = {"duration": round(budget, 3)} if engine in DURATION_ENGINES else {}
            result = provider.generate_audio(text, speaker=voice, language=target, **options)
            if not isinstance(result, dict) or not result.get("success"):
                raise RuntimeError(f"the TTS engine failed: {(result or {}).get('error', 'no audio')}")
            samples, rate = decode_wav(base64.b64decode(result.get("audio_base64") or result.get("audio") or ""))
            fit = plan_fit(len(samples) / rate, budget)
            if fit.status != "over" or shortenings >= MAX_SHORTENINGS or translator is None or person:
                break
            line = LineToTranslate(segment["id"], segment["speaker"], segment["source_text"], budget)
            shorter = translator.shorten(line, text, target=target, took_seconds=len(samples) / rate)
            saved = save_translation(segment["id"], shorter, revision)
            if saved is None:
                moved_on = True  # a person edited the line meanwhile: leave it for them
                break
            if saved == revision:
                break  # no shorter wording came back: keep this take, flagged as over
            text, revision = shorter, saved
            shortenings += 1
        if moved_on:
            counts["edited_meanwhile"] = counts.get("edited_meanwhile", 0) + 1
            continue
        if fit.tempo != 1.0:
            samples = time_stretch(samples, rate, fit.tempo)
        status = "shortened" if shortenings and fit.status in {"fits", "stretched"} else fit.status
        wav, watermark = watermark_render(encode_wav(samples, rate))
        asset_id = run.store(name=f"take-{_safe(segment['id'])}-r{revision}.wav", data=wav, kind="dub_take",
                             mime="audio/wav", title=f"Line {segment['position'] + 1} ({segment['speaker']})",
                             parents=[run.project["assets"].get("vocals", "")],
                             metadata={"text": text, "voice": voice, "engine": engine, "revision": revision,
                                       **({"watermark": watermark} if watermark else {})})
        save_take(segment["id"], asset_id=asset_id, revision=revision, seconds=round(len(samples) / rate, 3),
                  fit_status=status, fit_ratio=round(fit.ratio, 4), shortenings=shortenings)
        counts[status] = counts.get(status, 0) + 1
    return {"fit": counts}


def mux(run: StepRun) -> dict[str, Any]:
    """The dubbed mix over the ducked background, the dubbed video, and target-language subtitles."""
    from app.platform.voice.contracts import TranscriptDocument, export_transcript, watermark_render

    from .mix import PlacedTake, mix_dub

    if not run.segments:
        raise DubRequestError("there are no lines to mix")
    waiting = [segment for segment in run.segments if not approved(segment)]
    if waiting:
        raise DubRequestError(f"{len(waiting)} line(s) still need approval; the final mix waits for every line")
    background, rate = decode_wav(run.asset_bytes("background"))
    background = resample(background, rate, MIX_RATE)
    takes = []
    for segment in run.segments:
        samples, take_rate = decode_wav(run.bytes_of(segment["take_asset_id"]))
        takes.append(PlacedTake(segment["start_seconds"], resample(samples, take_rate, MIX_RATE)))
    mix, watermark = watermark_render(encode_wav(mix_dub(takes, background, MIX_RATE), MIX_RATE))
    title, target = run.project["title"], run.project["target_language"]
    mix_id = run.store(name="dub-mix.wav", data=mix, kind="dub_mix", mime="audio/wav", title=f"{title} ({target} dub)",
                       parents=[run.project["assets"].get("background", "")],
                       metadata={"language": target, **({"watermark": watermark} if watermark else {})})
    document = TranscriptDocument.model_validate({"language": target, "segments": [
        {"start": segment["start_seconds"], "end": segment["end_seconds"], "speaker": segment["speaker"],
         "text": segment["translation"], "words": []} for segment in run.segments]}).normalized()
    assets = {"mix": mix_id}
    for fmt in ("srt", "vtt"):
        text, mime = export_transcript(document, fmt)
        assets[fmt] = run.store(name=f"subtitles.{target}.{fmt}", data=text.encode("utf-8"), kind="dub_subtitles",
                                mime=mime, title=f"{title} ({target} subtitles, {fmt.upper()})", parents=[mix_id])
    from app.assets import default_asset_store

    source = default_asset_store().get_asset(run.project["source_asset_id"])
    suffix = Path(str(getattr(source, "storage_path", "") or "video.mp4")).suffix.lower()
    suffix = suffix if suffix in VIDEO_SUFFIXES else ".mp4"
    audio_codec = ["-c:a", "libopus", "-b:a", "160k"] if suffix == ".webm" else ["-c:a", "aac", "-b:a", "192k"]
    with tempfile.TemporaryDirectory(prefix="omnix-dub-") as work:
        video = Path(work) / f"source{suffix}"
        video.write_bytes(run.asset_bytes("source", max_bytes=MAX_VIDEO_BYTES))
        audio = Path(work) / "dub.wav"
        audio.write_bytes(mix)
        output = Path(work) / f"dubbed{suffix}"
        run_ffmpeg(["-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                    *audio_codec, "-shortest", str(output)])
        data = output.read_bytes()
    assets["video"] = run.store(name=f"dubbed.{target}{suffix}", data=data, kind="dub_video", mime=VIDEO_SUFFIXES[suffix],
                                title=f"{title} ({target} dub)", parents=[run.project["source_asset_id"], mix_id])
    return {"assets": assets}


__all__ = [
    "CHAINED",
    "DubRequestError",
    "MIX_RATE",
    "STEPS",
    "StepRun",
    "approved",
    "cast",
    "decode_wav",
    "encode_wav",
    "ingest",
    "mux",
    "needs_take",
    "needs_translation",
    "resample",
    "separate",
    "source_key",
    "synthesize",
    "take_is_current",
    "transcribe",
    "translate",
]
