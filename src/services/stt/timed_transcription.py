"""Timed, speaker-labelled batch transcription for the STT service (Voice Studio Phase 2).

- Words and their timing come from NeMo Parakeet-TDT (v3: 25 European languages;
  v2: English), loaded from ``resources/models/stt`` where the Models tool puts it.
- Speakers come from TitaNet speaker embeddings (CC-BY-4.0, part of NeMo), one
  per pause-delimited utterance of at most 3 s, clustered by average linkage on
  cosine distance (numpy). A requested speaker count fixes the number of
  clusters; otherwise the cut with the best silhouette decides. The whole file
  is diarized at once, so a speaker keeps one label across ASR chunks.
- Word edges that border a pause are snapped to the speech energy there
  (``refine_edges``): the ASR's timing is on an 80 ms grid and drifts at pauses.
- Long files are split into chunks of at most 30 s, cut at the quietest point
  near each boundary so no word straddles a cut; word times are shifted back
  onto the file's timeline.
- Both models are exempt helpers (Phase 1 §6): they load beside the live
  Nemotron model when free VRAM allows, fail fast otherwise, and unload after
  ``IDLE_UNLOAD_SECONDS`` without work. Batch work runs on one thread of its own
  and pauses between chunks while live speech is streaming.
"""
from __future__ import annotations

import asyncio
import logging
import math
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np
from fastapi import File, Form, HTTPException, UploadFile

from services.helper_models import HelperModel, HelperUnavailable, free_vram_gb

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000
CHUNK_SECONDS = 30.0
CUT_SEARCH_SECONDS = 2.0
UNIT_PAUSE_SECONDS = 0.3
UNIT_MAX_SECONDS = 3.0
UNIT_MIN_SECONDS = 1.0
# A speaker split must make units clearly closer to their own speaker than to the next,
# give every speaker a few units, and put speaker centroids well apart (random splits of
# one voice land around 0.05-0.15; different people are usually above 0.5).
MIN_SILHOUETTE = 0.12
MIN_CENTROID_DISTANCE = 0.3
MIN_SPEAKER_UNITS = 2
MIN_SPEAKER_SHARE = 0.04
MAX_SPEAKERS = 8
MAX_CLUSTER_POINTS = 600
SEGMENT_GAP_SECONDS = 1.0
SEGMENT_MAX_SECONDS = 15.0
IDLE_UNLOAD_SECONDS = 300.0
ASR_VRAM_GB = 2.5
SPEAKER_VRAM_GB = 1.0
TRANSCRIPT_SCHEMA = "omnix-transcript-v1"

BATCH_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="omnix-stt-batch")


class TimedTranscriptionUnavailable(HelperUnavailable):
    """A model is missing or does not fit; the message says what to do."""


def models_root() -> Path:
    from app.runtime.paths import resources_models_root

    return resources_models_root() / "stt"


def _checkpoint(folder_names: tuple[str, ...]) -> Path | None:
    from app.models.local import installed_snapshot

    for name in folder_names:
        # The desktop app keeps the pinned model in its packs folder (names are catalog ids there).
        snapshot = installed_snapshot(name)
        if snapshot is not None:
            found = sorted(snapshot.glob("*.nemo"))
            if found:
                return found[0]
    for name in folder_names:
        folder = models_root() / name
        if folder.is_dir():
            found = sorted(folder.glob("*.nemo"))
            if found:
                return found[0]
    return None


class _NemoHelper(HelperModel):
    """A NeMo checkpoint from the Speech models folder, loaded as an exempt helper."""

    unavailable = TimedTranscriptionUnavailable

    def __init__(self, label: str, folders: tuple[str, ...], vram_gb: float, loader: Callable[[Path], Any]) -> None:
        self.folders = folders
        super().__init__(label, vram_gb, lambda: loader(self._checkpoint()))

    def _checkpoint(self) -> Path:
        checkpoint = _checkpoint(self.folders)
        if checkpoint is None:
            raise TimedTranscriptionUnavailable(
                f"{self.label} is not installed; install it from Voice Studio's Models tool")
        return checkpoint

    def get(self) -> Any:
        if not self.loaded:
            self._checkpoint()  # a missing model says how to install it before any VRAM talk
        return super().get()


def _load_asr(checkpoint: Path) -> Any:
    import nemo.collections.asr as nemo_asr

    model = nemo_asr.models.ASRModel.restore_from(str(checkpoint), map_location="cuda" if free_vram_gb() is not None else "cpu")
    model.eval()
    return model


def _load_speaker(checkpoint: Path) -> Any:
    from nemo.collections.asr.models import EncDecSpeakerLabelModel

    model = EncDecSpeakerLabelModel.restore_from(str(checkpoint), map_location="cuda" if free_vram_gb() is not None else "cpu")
    model.eval()
    return model


ASR = _NemoHelper("Parakeet-TDT", ("parakeet-tdt-0.6b-v3", "parakeet-tdt-0.6b-v2"), ASR_VRAM_GB, _load_asr)
SPEAKERS = _NemoHelper("TitaNet speaker embeddings", ("speakerverification_en_titanet_large", "titanet-large"),
                        SPEAKER_VRAM_GB, _load_speaker)


def unload_idle_models() -> list[str]:
    return [model.label for model in (ASR, SPEAKERS) if model.unload_if_idle(IDLE_UNLOAD_SECONDS)]


# --- Audio and chunking -------------------------------------------------------------------------


def chunk_bounds(samples: np.ndarray, rate: int = SAMPLE_RATE, *, chunk_seconds: float = CHUNK_SECONDS,
                 search_seconds: float = CUT_SEARCH_SECONDS) -> list[tuple[int, int]]:
    """Chunks of at most ``chunk_seconds``, each cut at the quietest 20 ms near its nominal end."""
    total = len(samples)
    chunk = int(chunk_seconds * rate)
    if total <= chunk:
        return [(0, total)]
    frame = max(1, int(rate * 0.02))
    bounds: list[tuple[int, int]] = []
    start = 0
    while start < total:
        nominal = start + chunk
        if nominal >= total:
            bounds.append((start, total))
            break
        low = max(start + frame, nominal - int(search_seconds * rate))
        region = samples[low:nominal]
        count = max(1, len(region) // frame)
        energies = np.sqrt(np.mean(region[: count * frame].reshape(count, frame) ** 2, axis=1) + 1e-12)
        cut = low + int(np.argmin(energies)) * frame + frame // 2
        bounds.append((start, cut))
        start = cut
    return bounds


# --- Word edges at pauses -----------------------------------------------------------------------


EDGE_SEARCH_SECONDS = 0.25
EDGE_PAUSE_SECONDS = 0.15
EDGE_DROP_DB = 20.0


def _frame_db(samples: np.ndarray, rate: int = SAMPLE_RATE) -> np.ndarray:
    frame = int(rate * 0.01)
    count = len(samples) // frame
    if not count:
        return np.zeros(0)
    energy = np.mean(samples[: count * frame].reshape(count, frame).astype(np.float64) ** 2, axis=1)
    return 10 * np.log10(energy + 1e-12)


def refine_edges(samples: np.ndarray, words: list[dict[str, Any]], rate: int = SAMPLE_RATE) -> None:
    """Snap word edges that border a pause to where the speech energy starts or stops.

    The ASR's timing comes on an 80 ms grid and drifts at pauses; subtitles and
    clone samples are cut exactly there. A word that starts after a pause starts
    at the first 10 ms frame within ``EDGE_SEARCH_SECONDS`` whose level is within
    ``EDGE_DROP_DB`` of the word's own loudness (likewise for ends); edges never
    cross a neighbouring word or invert a word.
    """
    levels = _frame_db(samples, rate)
    if not len(levels):
        return
    step = 0.01

    def frame(time_point: float) -> int:
        return min(len(levels), max(0, int(round(time_point / step))))

    for index, word in enumerate(words):
        start, end = float(word["start"]), float(word["end"])
        loud = levels[frame(start): max(frame(start) + 1, frame(end))]
        if not len(loud):
            continue
        threshold = float(np.percentile(loud, 90)) - EDGE_DROP_DB
        previous_end = float(words[index - 1]["end"]) if index else 0.0
        next_start = float(words[index + 1]["start"]) if index + 1 < len(words) else len(levels) * step
        if index == 0 or start - previous_end >= EDGE_PAUSE_SECONDS:
            low = frame(max(previous_end, start - EDGE_SEARCH_SECONDS))
            high = frame(min(end - 0.05, start + EDGE_SEARCH_SECONDS))
            above = np.nonzero(levels[low:high] >= threshold)[0]
            if len(above):
                word["start"] = round((low + int(above[0])) * step, 3)
        if index + 1 == len(words) or next_start - end >= EDGE_PAUSE_SECONDS:
            low = frame(max(float(word["start"]) + 0.05, end - EDGE_SEARCH_SECONDS))
            high = frame(min(next_start, end + EDGE_SEARCH_SECONDS))
            above = np.nonzero(levels[low:high] >= threshold)[0]
            if len(above):
                word["end"] = round((low + int(above[-1]) + 1) * step, 3)


# --- Diarization --------------------------------------------------------------------------------


_SENTENCE_ENDS = (".", "?", "!", "…", "。", "？", "！")


class SpeechUnit(NamedTuple):
    start: float
    end: float
    # Seconds of words in the unit before any widening: short units embed less reliably.
    spoken: float


def speech_units(words: list[dict[str, Any]], duration: float, *, pause: float = UNIT_PAUSE_SECONDS,
                 longest: float = UNIT_MAX_SECONDS, shortest: float = UNIT_MIN_SECONDS) -> list[SpeechUnit]:
    """Stretches of speech to embed: words split at pauses and sentence ends, at most ``longest`` s each.

    Speaker turns change at pauses and sentence ends, so a unit rarely holds two
    speakers; silence never gets a unit. Units shorter than ``shortest`` are widened
    around their middle (clipped to the file) so the embedding has enough audio.
    """
    units: list[tuple[float, float]] = []
    current: list[tuple[float, float]] = []
    sentence_ended = False
    for word in words:
        start, end = float(word["start"]), float(word["end"])
        if current and (sentence_ended or start - current[-1][1] >= pause or end - current[0][0] > longest):
            units.append((current[0][0], current[-1][1]))
            current = []
        current.append((start, end))
        # Turns change at sentence ends far more often than inside a sentence.
        sentence_ended = _ends_sentence(str(word.get("word") or ""))
    if current:
        units.append((current[0][0], current[-1][1]))
    widened = []
    for start, end in units:
        spoken = end - start
        if spoken < shortest:
            middle = (start + end) / 2
            start, end = max(0.0, middle - shortest / 2), min(duration, middle + shortest / 2)
        widened.append(SpeechUnit(start, end, spoken))
    return widened


def _cosine_distances(points: np.ndarray) -> np.ndarray:
    return np.clip(1.0 - points @ points.T, 0.0, 2.0)


def _dendrogram(distance: np.ndarray) -> list[tuple[int, int]]:
    """Average-linkage merges, closest pair first: ``(kept, absorbed)`` row indices."""
    count = len(distance)
    distance = distance.copy()
    np.fill_diagonal(distance, np.inf)
    sizes = np.ones(count)
    merges: list[tuple[int, int]] = []
    for _ in range(count - 1):
        first, second = divmod(int(np.argmin(distance)), count)
        # Lance-Williams update for average linkage; ``second`` joins ``first``.
        merged = (sizes[first] * distance[first] + sizes[second] * distance[second]) / (sizes[first] + sizes[second])
        distance[first, :] = merged
        distance[:, first] = merged
        distance[first, first] = np.inf
        distance[second, :] = np.inf
        distance[:, second] = np.inf
        sizes[first] += sizes[second]
        merges.append((first, second))
    return merges


def _cut(count: int, merges: list[tuple[int, int]], clusters: int) -> np.ndarray:
    """A cluster id per row after replaying merges until ``clusters`` remain."""
    members = np.arange(count)
    for first, second in merges[: max(0, count - clusters)]:
        members[members == second] = first
    return members


def _silhouette(distance: np.ndarray, labels: np.ndarray) -> float:
    """Mean silhouette: how much closer each point is to its own cluster than to the nearest other one."""
    clusters = np.unique(labels)
    if len(clusters) < 2:
        return 0.0
    scores = []
    for index in range(len(labels)):
        own = labels == labels[index]
        if own.sum() <= 1:
            scores.append(0.0)
            continue
        inside = distance[index, own].sum() / (own.sum() - 1)
        outside = min(distance[index, labels == cluster].mean() for cluster in clusters if cluster != labels[index])
        scores.append((outside - inside) / max(inside, outside, 1e-12))
    return float(np.mean(scores))


def _centroids(points: np.ndarray, members: np.ndarray) -> tuple[list[int], np.ndarray]:
    ids = sorted(set(members.tolist()))
    centroids = np.vstack([points[members == cluster].mean(axis=0) for cluster in ids])
    return ids, centroids / np.maximum(np.linalg.norm(centroids, axis=1, keepdims=True), 1e-12)


def _distinct_speakers(points: np.ndarray, members: np.ndarray) -> bool:
    """Whether a split looks like different people rather than one voice cut in pieces."""
    _ids, centroids = _centroids(points, members)
    floor = max(MIN_SPEAKER_UNITS, math.ceil(MIN_SPEAKER_SHARE * len(points)))
    if min(np.bincount(np.unique(members, return_inverse=True)[1])) < floor:
        return False
    apart = 1.0 - centroids @ centroids.T
    np.fill_diagonal(apart, np.inf)
    return float(apart.min()) >= MIN_CENTROID_DISTANCE


def cluster_speakers(embeddings: np.ndarray, *, speakers: int | None = None,
                     reliable: np.ndarray | None = None) -> np.ndarray:
    """A speaker label per embedding, numbered by first appearance (Speaker 1 speaks first).

    Average-linkage clustering on cosine distance over the ``reliable`` units
    (enough speech for a steady embedding; all of them when unspecified). Without
    a requested count, the cut with the best silhouette wins when it reaches
    ``MIN_SILHOUETTE`` and its speakers are distinct (``_distinct_speakers``);
    otherwise everything is one speaker. Long files cluster an even sample of
    ``MAX_CLUSTER_POINTS`` units. Units left out of the clustering take the label
    of their nearest speaker centroid.
    """
    count = len(embeddings)
    if count <= 1:
        return np.zeros(count, dtype=int)
    normalized = embeddings / np.maximum(np.linalg.norm(embeddings, axis=1, keepdims=True), 1e-12)
    pool = np.arange(count)
    if reliable is not None and int(np.count_nonzero(reliable)) >= 2:
        pool = np.nonzero(reliable)[0]
    sample = pool[np.unique(np.linspace(0, len(pool) - 1, min(len(pool), MAX_CLUSTER_POINTS)).round().astype(int))]
    points = normalized[sample]
    distance = _cosine_distances(points)
    merges = _dendrogram(distance)
    if speakers:
        members = _cut(len(sample), merges, min(int(speakers), len(sample)))
    else:
        members, best = np.zeros(len(sample), dtype=int), MIN_SILHOUETTE
        for clusters in range(2, min(MAX_SPEAKERS, len(sample) - 1) + 1):
            candidate = _cut(len(sample), merges, clusters)
            score = _silhouette(distance, candidate)
            if score > best and _distinct_speakers(points, candidate):
                members, best = candidate, score
    if len(sample) == count:
        labels = members
    else:
        ids, centroids = _centroids(points, members)
        labels = np.array(ids)[np.argmax(normalized @ centroids.T, axis=1)]
        labels[sample] = members
    order: dict[int, int] = {}
    for label in labels:
        order.setdefault(int(label), len(order))
    return np.array([order[int(label)] for label in labels])


def assign_speakers(words: list[dict[str, Any]], windows: list[SpeechUnit] | list[tuple[float, float]],
                    labels: np.ndarray) -> None:
    """Give each word the label of the unit nearest its middle: a covering unit first, else any unit.

    Widened short units can overlap a neighbour, so among the units covering a
    word the one centred closest to it wins.
    """
    if not len(labels):
        for word in words:
            word["speaker"] = "Speaker 1"
        return
    starts = np.array([float(window[0]) for window in windows])
    ends = np.array([float(window[1]) for window in windows])
    centers = (starts + ends) / 2
    for word in words:
        middle = (float(word["start"]) + float(word["end"])) / 2
        away = np.abs(centers - middle) + np.where((starts <= middle) & (middle <= ends), 0.0, 1e6)
        word["speaker"] = f"Speaker {int(labels[int(np.argmin(away))]) + 1}"


def _ends_sentence(word: str) -> bool:
    return word.rstrip("\"')»”").endswith(_SENTENCE_ENDS)


def build_segments(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Consecutive words of one speaker, broken at pauses and at ``SEGMENT_MAX_SECONDS``.

    A segment that runs too long breaks after its last sentence end, so a
    sentence stays in one segment whenever it can.
    """
    segments: list[dict[str, Any]] = []

    def start_segment(entries: list[dict[str, Any]], speaker: str) -> dict[str, Any]:
        segment = {"start": float(entries[0]["start"]), "end": float(entries[-1]["end"]), "speaker": speaker,
                   "words": entries}
        segments.append(segment)
        return segment

    for word in words:
        entry = {key: word[key] for key in ("start", "end", "word", "confidence")}
        current = segments[-1] if segments else None
        if (current is None or current["speaker"] != word["speaker"]
                or float(word["start"]) - current["end"] > SEGMENT_GAP_SECONDS):
            start_segment([entry], word["speaker"])
            continue
        if float(word["end"]) - current["start"] > SEGMENT_MAX_SECONDS:
            cut = max((index for index, item in enumerate(current["words"]) if _ends_sentence(str(item["word"]))),
                      default=None)
            if cut is None:
                start_segment([entry], word["speaker"])
                continue
            carried = current["words"][cut + 1:]
            current["words"] = current["words"][: cut + 1]
            current["end"] = float(current["words"][-1]["end"])
            start_segment(carried + [entry], word["speaker"])
            continue
        current["words"].append(entry)
        current["end"] = float(word["end"])
    for segment in segments:
        segment["text"] = " ".join(entry["word"] for entry in segment["words"]).strip()
    return segments


# --- The pipeline -------------------------------------------------------------------------------


def _asr_words(model: Any, chunk_path: str, offset: float) -> list[dict[str, Any]]:
    outputs = model.transcribe([chunk_path], timestamps=True, batch_size=1, verbose=False)
    hypothesis = outputs[0] if isinstance(outputs, list) else outputs
    if isinstance(hypothesis, list):
        hypothesis = hypothesis[0]
    stamps = getattr(hypothesis, "timestamp", None) or {}
    confidences = getattr(hypothesis, "word_confidence", None) or []
    words = []
    for index, entry in enumerate(stamps.get("word", [])):
        text = str(entry.get("word") or entry.get("char") or "").strip()
        if not text:
            continue
        confidence = None
        if index < len(confidences):
            try:
                confidence = round(float(confidences[index]), 3)
            except (TypeError, ValueError):
                confidence = None
        words.append({"word": text, "start": round(offset + float(entry["start"]), 3),
                      "end": round(offset + float(entry["end"]), 3), "confidence": confidence})
    return words


def transcribe_timed(samples: np.ndarray, *, language: str = "", diarize: bool = True, speakers: int | None = None,
                     live_active: Callable[[], bool] = lambda: False, workdir: Path) -> dict[str, Any]:
    """A ``TranscriptDocument`` for 16 kHz mono float samples."""
    import soundfile as sf

    duration = len(samples) / SAMPLE_RATE
    model = ASR.get()
    words: list[dict[str, Any]] = []
    for index, (start, end) in enumerate(chunk_bounds(samples)):
        while live_active():  # live speech first: batch waits between chunks
            time.sleep(0.25)
        chunk_path = workdir / f"chunk-{index}.wav"
        sf.write(str(chunk_path), samples[start:end], SAMPLE_RATE, subtype="PCM_16")
        words.extend(_asr_words(model, str(chunk_path), start / SAMPLE_RATE))
    refine_edges(samples, words)
    diarized = False
    if diarize and words:
        windows = speech_units(words, duration)
        if len(windows) >= 2:
            speaker_model = SPEAKERS.get()
            embeddings = []
            for window_start, window_end, _spoken in windows:
                piece = samples[int(window_start * SAMPLE_RATE): int(window_end * SAMPLE_RATE)]
                embeddings.append(_embedding(speaker_model, piece))
            reliable = np.array([unit.spoken >= UNIT_MIN_SECONDS for unit in windows])
            labels = cluster_speakers(np.vstack(embeddings), speakers=speakers, reliable=reliable)
            assign_speakers(words, windows, labels)
            diarized = True
    if not diarized:
        for word in words:
            word["speaker"] = "Speaker 1"
    segments = build_segments(words)
    return {
        "schema": TRANSCRIPT_SCHEMA,
        "language": language or "auto",
        "duration": round(duration, 3),
        "engine": ASR.label,
        "diarized": diarized,
        "speakers": sorted({segment["speaker"] for segment in segments}, key=lambda name: int(name.split()[-1])),
        "segments": segments,
        "text": " ".join(segment["text"] for segment in segments).strip(),
    }


def _embedding(model: Any, piece: np.ndarray) -> np.ndarray:
    import torch

    device = next(model.parameters()).device
    signal = torch.tensor(piece, dtype=torch.float32, device=device).unsqueeze(0)
    length = torch.tensor([signal.shape[1]], device=device)
    with torch.no_grad():
        _logits, embedding = model.forward(input_signal=signal, input_signal_length=length)
    return embedding.squeeze(0).float().cpu().numpy()


def word_boundary_error(reference: list[tuple[float, float]], words: list[dict[str, Any]]) -> float:
    """Median error between reference boundaries and the nearest word boundary (seconds)."""
    starts = np.array([float(word["start"]) for word in words])
    ends = np.array([float(word["end"]) for word in words])
    if not len(starts):
        return math.inf
    errors = []
    for start, end in reference:
        errors.append(float(np.min(np.abs(starts - start))))
        errors.append(float(np.min(np.abs(ends - end))))
    return float(np.median(errors))


# --- The service route ---------------------------------------------------------------------------


def pcm16_to_float(pcm16: bytes) -> np.ndarray:
    return np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0


def install_timed_transcription_routes(app: Any, *, decode: Callable[[bytes, str], tuple[bytes, float]],
                                       live_active: Callable[[], bool]) -> None:
    """``POST /transcribe/timed`` and ``GET /transcribe/timed/status`` on an STT service app.

    ``decode`` turns an upload into 16 kHz mono PCM16 (the service's FFmpeg path);
    ``live_active`` says whether live audio is streaming right now.
    """
    @app.get("/transcribe/timed/status")
    def timed_status() -> dict[str, object]:
        return {
            "asr": {"installed": _checkpoint(ASR.folders) is not None, "loaded": ASR.loaded},
            "speakers": {"installed": _checkpoint(SPEAKERS.folders) is not None, "loaded": SPEAKERS.loaded},
            "free_vram_gb": free_vram_gb(),
        }

    @app.post("/transcribe/timed/warm")
    async def warm_timed() -> dict[str, object]:
        """Load the batch engine ahead of a short utterance (push-to-talk); it unloads again when idle."""
        try:
            await asyncio.get_running_loop().run_in_executor(BATCH_EXECUTOR, ASR.get)
        except TimedTranscriptionUnavailable as exc:
            return {"ok": False, "code": "model_unavailable", "message": str(exc)}
        return {"ok": True, "loaded": True}

    @app.post("/transcribe/timed")
    async def transcribe_timed_route(
        file: UploadFile = File(...),  # noqa: B008 - FastAPI dependency default
        language: str = Form(""),  # noqa: B008
        diarize: bool = Form(True),  # noqa: B008
        speakers: int = Form(0),  # noqa: B008
    ) -> dict[str, Any]:
        payload = await file.read()
        if not payload:
            raise HTTPException(status_code=400, detail="empty_audio")
        if speakers < 0 or speakers > MAX_SPEAKERS:
            raise HTTPException(status_code=400, detail="invalid_request")

        def run() -> dict[str, Any]:
            pcm16, _duration = decode(payload, file.filename or "audio.wav")
            with tempfile.TemporaryDirectory(prefix="omnix-timed-") as workdir:
                return transcribe_timed(pcm16_to_float(pcm16), language=language.strip(), diarize=diarize,
                                        speakers=speakers or None, live_active=live_active, workdir=Path(workdir))

        # ModelServiceMiddleware replaces every error body, so outcomes the caller acts on (a model to
        # install, VRAM to free, audio it cannot read) travel as 200 envelopes written by this code.
        try:
            return await asyncio.get_running_loop().run_in_executor(BATCH_EXECUTOR, run)
        except TimedTranscriptionUnavailable as exc:
            return {"ok": False, "code": "model_unavailable", "message": str(exc)}
        except RuntimeError:
            logger.warning("Timed transcription could not decode %s", file.filename, exc_info=True)
            return {"ok": False, "code": "decode_failed", "message": "The audio could not be decoded"}

    @app.on_event("startup")
    async def unload_idle_helpers() -> None:
        async def loop() -> None:
            while True:
                await asyncio.sleep(60)
                for label in await asyncio.get_running_loop().run_in_executor(BATCH_EXECUTOR, unload_idle_models):
                    logger.info("Unloaded idle %s", label)

        app.state.timed_unload_task = asyncio.create_task(loop())


__all__ = [
    "ASR",
    "BATCH_EXECUTOR",
    "SPEAKERS",
    "TRANSCRIPT_SCHEMA",
    "TimedTranscriptionUnavailable",
    "assign_speakers",
    "build_segments",
    "chunk_bounds",
    "cluster_speakers",
    "install_timed_transcription_routes",
    "refine_edges",
    "SpeechUnit",
    "speech_units",
    "transcribe_timed",
    "unload_idle_models",
    "word_boundary_error",
]
