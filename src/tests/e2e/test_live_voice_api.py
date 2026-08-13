"""Five-turn API exercise for the production Live Voice streaming pipeline.

The suite stays browserless, but it mirrors the latency-critical orchestration
used by browser live chat:

* segmented PCM WebSocket STT at ``/ws/transcribe``;
* incremental SSE chat at ``/api/chat/sessions/{id}/messages/stream``;
* committed clauses are queued to TTS while the LLM is still streaming;
* one persistent TTS WebSocket at ``/api/tts/live-call/websocket``; and
* first playback is modeled at the browser's 80 ms adaptive startup floor.

The modeled playback marker is intentionally not presented as physical speaker
playback. It exists so this API-only suite can measure the same first-frame
boundary without requiring AudioWorklet. Browser hardware runs remain the
authority for actual audible playback and underrun/rebuffer behavior.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import subprocess
import time
import uuid
import wave
from array import array
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp
import pytest
from websockets import connect as websocket_connect

RUN_API_TEST = os.environ.get("OMNIX_RUN_LIVE_VOICE_API", "0") == "1"
ROOT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_AUDIO_DIR = ROOT_DIR / "examples" / "voice"
DEFAULT_MANIFEST_DIR = ROOT_DIR / "resources" / "logs" / "benchmarks"

STT_SAMPLE_RATE = 16_000
STT_FRAME_SAMPLES = 320
STT_OVERLAP_SAMPLES = STT_SAMPLE_RATE * 300 // 1_000
TTS_SAMPLE_RATE = 24_000
TTS_START_BUFFER_MS = 80.0
TTS_START_BUFFER_SAMPLES = round(TTS_SAMPLE_RATE * TTS_START_BUFFER_MS / 1_000)
# The live-call startup policy transfers the first two-step decoder chunk as
# one 160 ms frame. Playback may still start at the modeled 80 ms floor because
# that first atomic frame already exceeds the required reserve.
TTS_EXPECTED_FRAME_SAMPLES = 3_840
TTS_MAX_PHRASE_CHARS = 220
TTS_SOFT_CLAUSE_CHARS = 96

STT_TIMEOUT_SECONDS = 120.0
CHAT_TIMEOUT_SECONDS = 180.0
TTS_TIMEOUT_SECONDS = 180.0


def _console_log(event: str, **details: Any) -> None:
    suffix = f" {json.dumps(details, default=str, sort_keys=True)}" if details else ""
    print(f"[live_voice_api] {event}{suffix}", flush=True)


def _preview(value: str, limit: int = 160) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized if len(normalized) <= limit else f"{normalized[:limit - 1]}…"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _base_url(value: str) -> str:
    return value.rstrip("/")


def _websocket_url(http_url: str, path: str) -> str:
    parsed = urlsplit(http_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunsplit((scheme, parsed.netloc, path, "", ""))


def _delta_ms(started_at: float | None, ended_at: float | None) -> float | None:
    if started_at is None or ended_at is None:
        return None
    return (ended_at - started_at) * 1_000


def _git_provenance() -> dict[str, Any]:
    def git(*arguments: str) -> str:
        try:
            completed = subprocess.run(
                ["git", *arguments],
                cwd=ROOT_DIR,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        # Keep the leading status column from ``git status --porcelain``. A
        # full ``strip`` corrupts the first path when its index column is blank.
        return completed.stdout.rstrip() if completed.returncode == 0 else ""

    status_lines = [line for line in git("status", "--porcelain").splitlines() if line]
    return {
        "git_sha": git("rev-parse", "HEAD") or None,
        "git_branch": git("branch", "--show-current") or None,
        "working_tree_dirty": bool(status_lines),
        "working_tree_dirty_file_count": len(status_lines),
        "working_tree_dirty_files": [line[3:] if len(line) > 3 else line for line in status_lines],
    }


def _audio_paths() -> list[Path]:
    configured = os.environ.get("OMNIX_LIVE_VOICE_API_AUDIO_DIR", "").strip()
    audio_dir = Path(configured).expanduser() if configured else DEFAULT_AUDIO_DIR
    paths = [audio_dir / f"interaction-{index}.wav" for index in range(1, 6)]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        pytest.fail(f"Missing Live Voice API audio files: {missing}")
    return paths


def _read_pcm16(path: Path) -> tuple[int, bytes]:
    try:
        with wave.open(str(path), "rb") as source:
            if source.getnchannels() != 1 or source.getsampwidth() != 2:
                pytest.fail(f"{path} must be mono 16-bit PCM WAV")
            return source.getframerate(), source.readframes(source.getnframes())
    except (OSError, wave.Error) as exc:
        pytest.fail(f"Could not read {path}: {exc}")


def _resample_pcm16(audio: bytes, source_rate: int, target_rate: int) -> bytes:
    """Match the browser's linear Float32 resampling and PCM16 encoding."""

    if source_rate == target_rate:
        return audio
    if len(audio) % 2:
        raise ValueError("PCM16 input contains a partial sample")
    source = array("h")
    source.frombytes(audio)
    if not source:
        return b""
    output_length = max(1, round(len(source) * target_rate / source_rate))
    output = array("h")
    ratio = source_rate / target_rate
    for index in range(output_length):
        position = index * ratio
        lower = min(len(source) - 1, int(position))
        upper = min(len(source) - 1, lower + 1)
        fraction = position - lower
        value = (source[lower] / 32768.0) * (1.0 - fraction) + (source[upper] / 32768.0) * fraction
        output.append(max(-32768, min(32767, int(value * 32767))))
    return output.tobytes()


def _sse_events(buffer: str) -> tuple[list[dict[str, Any]], str]:
    blocks = buffer.split("\n\n")
    pending = blocks.pop() or ""
    events: list[dict[str, Any]] = []
    for block in blocks:
        for line in block.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload:
                continue
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                events.append(parsed)
    return events, pending


class StreamingPhraseAccumulator:
    """Emit only text that is stable enough to synthesize while SSE continues."""

    def __init__(self) -> None:
        self.pending = ""

    def push(self, chunk: str) -> list[str]:
        if not chunk:
            return []
        self.pending += chunk
        return self._drain(final=False)

    def finish(self) -> list[str]:
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> list[str]:
        phrases: list[str] = []
        while True:
            candidate = self.pending
            if not candidate.strip():
                self.pending = ""
                return phrases

            split_at = self._hard_boundary(candidate)
            if split_at is None and len(candidate) >= TTS_SOFT_CLAUSE_CHARS:
                split_at = self._soft_boundary(candidate)
            if split_at is None and len(candidate) > TTS_MAX_PHRASE_CHARS:
                split_at = self._word_boundary(candidate, TTS_MAX_PHRASE_CHARS)
            if split_at is None:
                if not final:
                    return phrases
                split_at = len(candidate)

            raw_phrase = candidate[:split_at]
            self.pending = candidate[split_at:]
            phrase = re.sub(r"\s+", " ", raw_phrase).strip()
            if phrase:
                phrases.append(phrase)

    @staticmethod
    def _hard_boundary(text: str) -> int | None:
        match = re.search(r"[.!?](?:[\"')\]]*)\s+", text)
        if match:
            return match.end()
        if "\n" in text:
            return text.index("\n") + 1
        return None

    @staticmethod
    def _soft_boundary(text: str) -> int | None:
        limit = min(len(text), TTS_MAX_PHRASE_CHARS)
        for punctuation in ("; ", ": ", ", "):
            index = text.rfind(punctuation, 0, limit)
            if index >= 48:
                return index + len(punctuation)
        return None

    @staticmethod
    def _word_boundary(text: str, limit: int) -> int:
        split_at = text.rfind(" ", 0, limit + 1)
        return split_at + 1 if split_at > 0 else limit


@dataclass
class DiagnosticReporter:
    http: aiohttp.ClientSession
    base_url: str
    trace_id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.perf_counter)
    closed: bool = False

    def record(self, event: str, details: dict[str, Any] | None = None, source: str = "api_test") -> None:
        if self.closed:
            return
        payload = {
            "client_wall_time_ms": round(time.time() * 1000, 3),
            "client_monotonic_ms": round((time.perf_counter() - self.started_at) * 1000, 3),
            "document_visibility": "visible",
        }
        payload.update(details or {})
        self.events.append({"source": source, "event": event, "details": payload})

    async def flush(self) -> None:
        if not self.events:
            return
        batch = self.events
        self.events = []
        endpoint = f"{self.base_url}/api/tts/live-call/diagnostics"
        _console_log("diagnostics message sent", event_count=len(batch), trace_id=self.trace_id)
        async with self.http.post(endpoint, json={"trace_id": self.trace_id, "events": batch}) as response:
            _console_log("diagnostics response received", status=response.status, trace_id=self.trace_id)
            if response.status >= 400:
                body = await response.text()
                raise RuntimeError(f"Live-call diagnostics returned HTTP {response.status}: {body[:240]}")

    async def close(self, event: str, details: dict[str, Any] | None = None) -> None:
        if self.closed:
            return
        self.record(event, details, "controller")
        self.closed = True
        await self.flush()


@dataclass
class TurnResult:
    index: int
    audio_file: str
    input_rate: int
    input_samples: int
    run_state: str = "cold"
    stt_text_chars: int = 0
    llm_text_chars: int = 0
    tts_phrase_count: int = 0
    tts_audio_bytes: int = 0
    tts_sample_rate: int | None = None
    stt_finalize_ms: float | None = None
    final_to_first_token_ms: float | None = None
    first_token_to_tts_request_ms: float | None = None
    tts_request_to_first_pcm_ms: float | None = None
    first_pcm_to_playback_ms: float | None = None
    final_to_first_playback_ms: float | None = None
    stt_to_first_tts_ms: float | None = None
    stt_to_first_playback_ms: float | None = None
    speech_end_to_final_ms: float | None = None
    speech_end_to_first_tts_ms: float | None = None
    speech_end_to_first_playback_ms: float | None = None
    llm_completion_after_first_tts_ms: float | None = None
    streaming_tts_overlap: bool = False
    playback_mode: str = "adaptive_api_model"
    completed: bool = False
    stt_started_at: float | None = field(default=None, repr=False)
    speech_ended_at: float | None = field(default=None, repr=False)
    final_received_at: float | None = field(default=None, repr=False)
    first_llm_chunk_at: float | None = field(default=None, repr=False)
    llm_completed_at: float | None = field(default=None, repr=False)
    first_tts_request_at: float | None = field(default=None, repr=False)
    first_pcm_at: float | None = field(default=None, repr=False)
    first_playback_at: float | None = field(default=None, repr=False)

    def metrics(self) -> dict[str, Any]:
        self.final_to_first_token_ms = _delta_ms(self.final_received_at, self.first_llm_chunk_at)
        self.first_token_to_tts_request_ms = _delta_ms(self.first_llm_chunk_at, self.first_tts_request_at)
        self.tts_request_to_first_pcm_ms = _delta_ms(self.first_tts_request_at, self.first_pcm_at)
        self.first_pcm_to_playback_ms = _delta_ms(self.first_pcm_at, self.first_playback_at)
        self.final_to_first_playback_ms = _delta_ms(self.final_received_at, self.first_playback_at)
        self.stt_to_first_tts_ms = _delta_ms(self.stt_started_at, self.first_pcm_at)
        self.stt_to_first_playback_ms = _delta_ms(self.stt_started_at, self.first_playback_at)
        self.speech_end_to_final_ms = _delta_ms(self.speech_ended_at, self.final_received_at)
        self.speech_end_to_first_tts_ms = _delta_ms(self.speech_ended_at, self.first_pcm_at)
        self.speech_end_to_first_playback_ms = _delta_ms(
            self.speech_ended_at,
            self.first_playback_at,
        )
        self.llm_completion_after_first_tts_ms = _delta_ms(self.first_tts_request_at, self.llm_completed_at)
        self.streaming_tts_overlap = bool(
            self.first_tts_request_at is not None
            and self.llm_completed_at is not None
            and self.first_tts_request_at < self.llm_completed_at
        )
        return {
            "final_to_first_token_ms": self.final_to_first_token_ms,
            "first_token_to_tts_request_ms": self.first_token_to_tts_request_ms,
            "tts_request_to_first_pcm_ms": self.tts_request_to_first_pcm_ms,
            "first_pcm_to_playback_ms": self.first_pcm_to_playback_ms,
            "final_to_first_playback_ms": self.final_to_first_playback_ms,
            "stt_to_first_tts_ms": self.stt_to_first_tts_ms,
            "stt_to_first_playback_ms": self.stt_to_first_playback_ms,
            "speech_end_to_final_ms": self.speech_end_to_final_ms,
            "speech_end_to_first_tts_ms": self.speech_end_to_first_tts_ms,
            "speech_end_to_first_playback_ms": self.speech_end_to_first_playback_ms,
            "llm_completion_after_first_tts_ms": self.llm_completion_after_first_tts_ms,
            "streaming_tts_overlap": self.streaming_tts_overlap,
            "playback_mode": self.playback_mode,
        }

    def manifest_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "stt_started_at",
            "speech_ended_at",
            "final_received_at",
            "first_llm_chunk_at",
            "llm_completed_at",
            "first_tts_request_at",
            "first_pcm_at",
            "first_playback_at",
        ):
            payload.pop(key, None)
        return payload


@dataclass
class TtsPhraseResult:
    audio_bytes: int
    sample_rate: int
    frame_count: int
    first_pcm_at: float
    first_playback_at: float
    first_audio_ms: float
    frame_samples: int


class ApiSttClient:
    def __init__(self, websocket: Any, reporter: DiagnosticReporter) -> None:
        self.websocket = websocket
        self.reporter = reporter
        self.session_id = f"stt-session-api-{uuid.uuid4().hex}"
        self.capture_epoch = f"capture-api-{uuid.uuid4().hex}"
        self.sample_rate = STT_SAMPLE_RATE
        self.frame_samples = STT_FRAME_SAMPLES
        self.provider = "parakeet"
        self.config_version = "legacy-default"
        self.absolute_sample = 0
        self.next_sequence = 0
        self.recent_overlap = b""
        self.audio_messages_sent = 0

    async def negotiate(self) -> None:
        ready = await self._receive_json(STT_TIMEOUT_SECONDS)
        if ready.get("type") != "ready":
            raise RuntimeError(f"Live STT did not negotiate: {ready!r}")
        self.provider = str(ready.get("provider") or self.provider)
        self.sample_rate = int(ready.get("sampleRate") or self.sample_rate)
        self.frame_samples = int(ready.get("frameSamples") or self.frame_samples)
        self.config_version = str(ready.get("configVersion") or self.config_version)
        protocol = str(ready.get("protocol") or "legacy")
        if protocol != "segmented-v1":
            raise RuntimeError(f"Live STT returned unsupported protocol: {protocol}")
        self.reporter.record(
            "stt_negotiated",
            {
                "provider": self.provider,
                "protocol": protocol,
                "sample_rate": self.sample_rate,
                "frame_samples": self.frame_samples,
                "encoding": ready.get("encoding", "pcm16le"),
                "capabilities": ready.get("capabilities", []),
                "config_version": self.config_version,
                "language": ready.get("language"),
            },
            "live_voice_controller",
        )
        await self.websocket.send(json.dumps({
            "type": "hello",
            "protocol": "segmented-v1",
            "sessionId": self.session_id,
            "captureEpoch": self.capture_epoch,
            "sampleRate": self.sample_rate,
            "configVersion": self.config_version,
            "language": ready.get("language") or "en-US",
        }))
        _console_log("STT message sent", type="hello", session_id=self.session_id)
        session_ready = await self._receive_until(lambda message: message.get("type") == "session_ready")
        if session_ready.get("provider"):
            self.provider = str(session_ready["provider"])

    async def send_turn(self, pcm16: bytes, turn: TurnResult) -> str:
        if len(pcm16) % 2:
            raise ValueError("STT PCM16 input contains a partial sample")
        segment_id = f"segment-api-{turn.index}-{uuid.uuid4().hex}"
        sequence = self.next_sequence
        self.next_sequence += 1
        primary_start = self.absolute_sample
        overlap_samples = len(self.recent_overlap) // 2
        capture_start = primary_start - overlap_samples

        if self.recent_overlap:
            await self._send_audio_frame(segment_id, sequence, capture_start, primary_start, capture_start, self.recent_overlap)

        frame_bytes = self.frame_samples * 2
        for offset in range(0, len(pcm16), frame_bytes):
            frame = pcm16[offset : offset + frame_bytes]
            sample_start = self.absolute_sample + offset // 2
            await self._send_audio_frame(segment_id, sequence, capture_start, primary_start, sample_start, frame)
            await asyncio.sleep(len(frame) / 2 / self.sample_rate)

        turn.speech_ended_at = time.perf_counter()
        self.absolute_sample += len(pcm16) // 2
        self.recent_overlap = pcm16[-STT_OVERLAP_SAMPLES * 2 :]
        finalize_request_id = f"finalize-api-{turn.index}-{uuid.uuid4().hex}"
        self.reporter.record("stt_final_requested", {
            "provider": self.provider,
            "segment_id": segment_id,
            "source_sequence": sequence,
            "finalize_request_id": finalize_request_id,
            "audio_samples": len(pcm16) // 2,
            "sample_rate": self.sample_rate,
            "speech_end_source": "fixture_audio_end",
        }, "live_voice_controller")
        await self.websocket.send(json.dumps({
            "type": "finalize",
            "protocol": "segmented-v1",
            "sessionId": self.session_id,
            "captureEpoch": self.capture_epoch,
            "segmentId": segment_id,
            "sequence": sequence,
            "finalizeRequestId": finalize_request_id,
            "captureStartSample": capture_start,
            "primaryStartSample": primary_start,
            "endSample": self.absolute_sample,
        }))
        _console_log("STT message sent", type="finalize", turn=turn.index, sequence=sequence, samples=self.absolute_sample)
        result = await self._receive_until(
            lambda message: message.get("type") == "result_available" and int(message.get("sequence", -1)) == sequence
        )
        turn.final_received_at = time.perf_counter()
        text = str(result.get("text") or "").strip()
        if not text:
            raise RuntimeError(f"Live STT returned an empty transcript for turn {turn.index}")
        metrics = result.get("providerMetrics")
        if isinstance(metrics, dict) and isinstance(metrics.get("finalize_ms"), (int, float)):
            turn.stt_finalize_ms = float(metrics["finalize_ms"])
        turn.stt_text_chars = len(text)
        _console_log("STT result received", turn=turn.index, type=result.get("type"), chars=len(text), text=_preview(text))
        self.reporter.record("stt_final_received", {
            "provider": result.get("provider") or self.provider,
            "segment_id": result.get("segmentId") or segment_id,
            "source_sequence": sequence,
            "result_id": result.get("resultId"),
            "finalize_request_id": result.get("finalizeRequestId") or finalize_request_id,
            "transcript_chars": len(text),
            "stt_finalize_ms": turn.stt_finalize_ms,
            "provider_metrics": metrics if isinstance(metrics, dict) else {},
        }, "live_voice_controller")
        return text

    async def _send_audio_frame(self, segment_id: str, sequence: int, capture_start: int, primary_start: int, sample_start: int, frame: bytes) -> None:
        self.audio_messages_sent += 1
        await self.websocket.send(json.dumps({
            "type": "audio",
            "protocol": "segmented-v1",
            "sessionId": self.session_id,
            "captureEpoch": self.capture_epoch,
            "segmentId": segment_id,
            "sequence": sequence,
            "captureStartSample": capture_start,
            "primaryStartSample": primary_start,
            "sampleStart": sample_start,
            "sampleEnd": sample_start + len(frame) // 2,
            "sampleRate": self.sample_rate,
            "data": base64.b64encode(frame).decode("ascii"),
        }))
        if self.audio_messages_sent == 1 or self.audio_messages_sent % 25 == 0:
            _console_log("STT audio message sent", count=self.audio_messages_sent, type="audio", sequence=sequence, bytes=len(frame))

    async def _receive_json(self, timeout: float) -> dict[str, Any]:
        raw = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
        if isinstance(raw, bytes):
            raise RuntimeError("Live STT returned an unexpected binary message")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Live STT returned an invalid message: {payload!r}")
        _console_log("STT message received", type=payload.get("type"), sequence=payload.get("sequence"))
        return payload

    async def _receive_until(self, predicate: Any) -> dict[str, Any]:
        while True:
            message = await self._receive_json(STT_TIMEOUT_SECONDS)
            message_type = message.get("type")
            if message_type in {"error", "segment_error"}:
                raise RuntimeError(f"Live STT failed: {message}")
            if predicate(message):
                return message


class ApiTtsClient:
    def __init__(self, websocket: Any, reporter: DiagnosticReporter, voice: str | None, session_id: str) -> None:
        self.websocket = websocket
        self.reporter = reporter
        self.voice = voice
        self.session_id = session_id
        self.output_order = 0

    async def synthesize(self, text: str, turn_index: int, phrase_index: int, turn_reporter: DiagnosticReporter) -> TtsPhraseResult:
        safe_session = re.sub(r"[^A-Za-z0-9_.-]+", "-", self.session_id)[-40:]
        output_id = f"conversation-{safe_session}-g{turn_index}-p{phrase_index}"[:120]
        stream_id = f"chat-live-api-g{turn_index}-p{phrase_index}-{uuid.uuid4().hex[:8]}"
        segment_id = f"speech-api-{turn_index}-{phrase_index}-{uuid.uuid4().hex}"
        started = time.perf_counter()
        self.reporter.record("phrase_request_sent", {
            "segment_id": segment_id,
            "phrase_index": phrase_index,
            "phrase_stream_id": stream_id,
            "output_id": output_id,
            "generation_epoch": turn_index,
            "output_order": self.output_order,
            "text_length": len(text),
            "websocket_reused": True,
        }, "pcm_session")
        output_order = self.output_order
        self.output_order += 1
        await self.websocket.send(json.dumps({
            "type": "synthesize",
            "request_id": stream_id,
            "phrase_index": phrase_index,
            "segment_id": segment_id,
            "output_id": output_id,
            "generation_epoch": turn_index,
            "output_order": output_order,
            "text": text,
            "speaker": self.voice,
            "language": "English",
            "chunk_size": 4,
            "temperature": 0.6,
            "top_k": 20,
            "top_p": 0.85,
            "repetition_penalty": 1.05,
            "append_silence": False,
            "non_streaming_mode": False,
            "parity_mode": False,
            "diagnostics_stream_id": stream_id,
            "pronunciation_lexicon": [],
        }))
        _console_log("TTS message sent", type="synthesize", turn=turn_index, phrase=phrase_index, chars=len(text), text=_preview(text))

        audio_bytes = 0
        frame_count = 0
        sample_rate: int | None = None
        frame_samples = 0
        buffered_samples = 0
        first_pcm_at: float | None = None
        first_playback_at: float | None = None
        while True:
            raw = await asyncio.wait_for(self.websocket.recv(), timeout=TTS_TIMEOUT_SECONDS)
            if isinstance(raw, bytes):
                if len(raw) % 2:
                    raise RuntimeError("Live TTS returned a partial PCM16 sample")
                now = time.perf_counter()
                audio_bytes += len(raw)
                frame_count += 1
                samples = len(raw) // 2
                buffered_samples += samples
                if first_pcm_at is None:
                    first_pcm_at = now
                    self.reporter.record("tts_first_audio_received", {
                        "phrase_index": phrase_index,
                        "output_id": output_id,
                        "generation_epoch": turn_index,
                        "bytes": len(raw),
                        "frame_count": frame_count,
                        "elapsed_ms": (now - started) * 1_000,
                    }, "pcm_session")
                    turn_reporter.record("tts_first_pcm_received", {
                        "phrase_index": phrase_index,
                        "output_id": output_id,
                        "generation_epoch": turn_index,
                        "frame_samples": samples,
                        "sample_rate": sample_rate or TTS_SAMPLE_RATE,
                    }, "api_test")

                resolved_rate = sample_rate or TTS_SAMPLE_RATE
                start_buffer_samples = round(resolved_rate * TTS_START_BUFFER_MS / 1_000)
                if first_playback_at is None and buffered_samples >= start_buffer_samples:
                    first_playback_at = now
                    turn_reporter.record("audio_playback_started", {
                        "playback_mode": "adaptive_api_model",
                        "physical_playback": False,
                        "phrase_index": phrase_index,
                        "output_id": output_id,
                        "generation_epoch": turn_index,
                        "buffered_samples": buffered_samples,
                        "start_buffer_samples": start_buffer_samples,
                        "start_buffer_ms": TTS_START_BUFFER_MS,
                        "sample_rate": resolved_rate,
                    }, "api_test")
                continue

            message = json.loads(raw)
            if not isinstance(message, dict):
                raise RuntimeError(f"Live TTS returned an invalid message: {message!r}")
            message_type = message.get("type")
            if message_type == "error":
                raise RuntimeError(f"Live TTS failed: {message}")
            if message_type in {"start", "format"}:
                if isinstance(message.get("sample_rate"), int):
                    sample_rate = int(message["sample_rate"])
                if message_type == "start":
                    frame_samples = int(message.get("frame_samples") or 0)
                    self.reporter.record("tts_stream_opened", {
                        "phrase_index": phrase_index,
                        "output_id": output_id,
                        "generation_epoch": turn_index,
                        "sample_rate": sample_rate,
                        "frame_samples": frame_samples,
                    }, "pcm_session")
                    if phrase_index == 0 and frame_samples != TTS_EXPECTED_FRAME_SAMPLES:
                        raise RuntimeError(f"Live TTS first phrase returned {frame_samples} frame samples; expected {TTS_EXPECTED_FRAME_SAMPLES}")
                continue
            if message_type != "done":
                continue
            if audio_bytes <= 0 or frame_count <= 0 or first_pcm_at is None:
                raise RuntimeError(f"Live TTS completed without audio for turn {turn_index}")
            if first_playback_at is None:
                raise RuntimeError(f"Live TTS never reached the {TTS_START_BUFFER_MS:.0f} ms modeled playback threshold on turn {turn_index}")
            self.reporter.record("phrase_buffered", {
                "phrase_index": phrase_index,
                "output_id": output_id,
                "generation_epoch": turn_index,
                "phrase_stream_id": stream_id,
                "frames": frame_count,
                "received_bytes": audio_bytes,
                "sample_rate": sample_rate,
                "elapsed_ms": (time.perf_counter() - started) * 1_000,
            }, "pcm_session")
            await self.websocket.send(json.dumps({
                "type": "diagnostic",
                "stream_id": stream_id,
                "event": "playback_finished",
                "details": {
                    "completion_scope": "output_item_buffered",
                    "segment_id": segment_id,
                    "phrase_index": phrase_index,
                    "output_id": output_id,
                    "generation_epoch": turn_index,
                    "frames": frame_count,
                    "received_bytes": audio_bytes,
                    "sample_rate": sample_rate,
                    "playback_mode": "adaptive_api_model",
                },
            }))
            return TtsPhraseResult(audio_bytes, sample_rate or TTS_SAMPLE_RATE, frame_count, first_pcm_at, first_playback_at, (first_pcm_at - started) * 1_000, frame_samples)


async def _tts_worker(queue: asyncio.Queue[tuple[int, str] | None], tts_client: ApiTtsClient, turn: TurnResult, reporter: DiagnosticReporter, llm_done: asyncio.Event) -> None:
    while True:
        item = await queue.get()
        try:
            if item is None:
                return
            phrase_index, phrase = item
            request_at = time.perf_counter()
            if turn.first_tts_request_at is None:
                turn.first_tts_request_at = request_at
            reporter.record("tts_request_started", {
                "phrase_index": phrase_index,
                "text_chars": len(phrase),
                "streaming_requested": True,
                "llm_stream_completed": llm_done.is_set(),
            }, "chatbot_workspace")
            result = await tts_client.synthesize(phrase, turn.index, phrase_index, reporter)
            turn.tts_phrase_count += 1
            turn.tts_audio_bytes += result.audio_bytes
            turn.tts_sample_rate = result.sample_rate
            if turn.first_pcm_at is None:
                turn.first_pcm_at = result.first_pcm_at
            if turn.first_playback_at is None:
                turn.first_playback_at = result.first_playback_at
        finally:
            queue.task_done()


async def _stream_chat_to_tts(http: aiohttp.ClientSession, api_url: str, session_id: str, transcript: str, turn_suffix: str, turn: TurnResult, reporter: DiagnosticReporter, tts_client: ApiTtsClient) -> str:
    voice_turn_id = f"voice-turn:{turn_suffix}"
    chat_payload: dict[str, Any] = {
        "content": transcript,
        "live_voice_turn_id": voice_turn_id,
        "user_turn_id": f"voice-user-turn:{turn_suffix}",
        "speech_segment_id": f"voice-segment:{turn_suffix}",
    }
    provider = os.environ.get("OMNIX_LIVE_VOICE_API_PROVIDER", "").strip()
    model = os.environ.get("OMNIX_LIVE_VOICE_API_MODEL", "").strip()
    if provider:
        chat_payload["provider_id"] = provider
    if model:
        chat_payload["model_id"] = model
    reporter.record("chat_submit_started", {
        "input_chars": len(transcript),
        "provider_configured": bool(provider),
        "model_configured": bool(model),
    }, "chatbot_workspace")

    phrase_queue: asyncio.Queue[tuple[int, str] | None] = asyncio.Queue()
    llm_done = asyncio.Event()
    tts_task = asyncio.create_task(_tts_worker(phrase_queue, tts_client, turn, reporter, llm_done), name=f"live-voice-api-tts-turn-{turn.index}")
    accumulator = StreamingPhraseAccumulator()
    response_text = ""
    phrase_index = 0
    chat_path = f"/api/chat/sessions/{session_id}/messages/stream"

    async def accept_event(event: dict[str, Any]) -> None:
        nonlocal response_text, phrase_index
        event_type = event.get("type")
        if event_type == "error":
            raise RuntimeError(str(event.get("message") or "Live chat stream failed"))
        if event_type != "text_chunk":
            return
        chunk_text = str(event.get("text") or "")
        if not chunk_text:
            return
        now = time.perf_counter()
        if turn.first_llm_chunk_at is None:
            turn.first_llm_chunk_at = now
            reporter.record("llm_first_text_chunk_received", {
                "text_chunk_chars": len(chunk_text),
                "elapsed_ms": _delta_ms(turn.final_received_at, now),
            }, "chatbot_workspace")
        response_text += chunk_text
        for phrase in accumulator.push(chunk_text):
            reporter.record("tts_phrase_committed", {
                "phrase_index": phrase_index,
                "text_chars": len(phrase),
                "commit_source": "incremental_llm",
            }, "chatbot_workspace")
            await phrase_queue.put((phrase_index, phrase))
            phrase_index += 1

    try:
        _console_log("HTTP message sent", method="POST", path=chat_path, turn=turn.index, chars=len(transcript), text=_preview(transcript))
        async with http.post(f"{api_url}{chat_path}", json=chat_payload, timeout=CHAT_TIMEOUT_SECONDS) as response:
            _console_log("HTTP response received", method="POST", path=chat_path, status=response.status, turn=turn.index)
            if response.status >= 400:
                body = await response.text()
                raise RuntimeError(f"Live chat stream failed: HTTP {response.status} {body[:240]}")
            reporter.record("chat_response_opened", {"status": response.status}, "chatbot_workspace")
            pending = ""
            async for chunk in response.content.iter_chunked(16_384):
                pending += chunk.decode("utf-8", errors="replace")
                events, pending = _sse_events(pending)
                for event in events:
                    await accept_event(event)
            if pending.strip():
                events, _ = _sse_events(f"{pending}\n\n")
                for event in events:
                    await accept_event(event)
        for phrase in accumulator.finish():
            reporter.record("tts_phrase_committed", {
                "phrase_index": phrase_index,
                "text_chars": len(phrase),
                "commit_source": "llm_stream_flush",
            }, "chatbot_workspace")
            await phrase_queue.put((phrase_index, phrase))
            phrase_index += 1
        turn.llm_completed_at = time.perf_counter()
        llm_done.set()
        reporter.record("llm_stream_completed", {
            "response_chars": len(response_text.strip()),
            "elapsed_ms": _delta_ms(turn.final_received_at, turn.llm_completed_at),
            "tts_already_started": turn.first_tts_request_at is not None and turn.first_tts_request_at < turn.llm_completed_at,
        }, "chatbot_workspace")
        await phrase_queue.put(None)
        await tts_task
    except BaseException:
        llm_done.set()
        if not tts_task.done():
            tts_task.cancel()
        await asyncio.gather(tts_task, return_exceptions=True)
        raise
    response_text = response_text.strip()
    if not response_text:
        raise RuntimeError(f"Live chat returned no assistant text for turn {turn.index}")
    return response_text


async def _run_api_test() -> dict[str, Any]:
    api_url = _base_url(os.environ.get("OMNIX_LIVE_VOICE_API_URL", "http://127.0.0.1:8000"))
    stt_url = _base_url(os.environ.get("OMNIX_LIVE_VOICE_API_STT_URL", "http://127.0.0.1:5201"))
    voice = os.environ.get("OMNIX_LIVE_VOICE_API_VOICE", "").strip() or None
    audio_paths = _audio_paths()
    provenance = _git_provenance()
    _console_log("live voice API test started", api_url=api_url, stt_url=stt_url, turns=len(audio_paths), streaming_chat_to_tts=True, modeled_start_buffer_ms=TTS_START_BUFFER_MS)
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=20, sock_read=CHAT_TIMEOUT_SECONDS)
    manifest_path = Path(os.environ.get(
        "OMNIX_LIVE_VOICE_API_MANIFEST",
        DEFAULT_MANIFEST_DIR / f"live-voice-api-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{os.getpid()}.json",
    ))
    manifest: dict[str, Any] = {
        "schema_version": 3,
        "started_at_utc": _utc_now(),
        "provenance": provenance,
        "api_base_url": api_url,
        "stt_base_url": stt_url,
        "audio_files": [str(path.resolve()) for path in audio_paths],
        "streaming_model": {
            "incremental_llm_to_tts": True,
            "persistent_tts_websocket": True,
            "playback_mode": "adaptive_api_model",
            "physical_playback": False,
            "start_buffer_ms": TTS_START_BUFFER_MS,
            "start_buffer_samples": TTS_START_BUFFER_SAMPLES,
            "expected_first_frame_samples": TTS_EXPECTED_FRAME_SAMPLES,
            "speech_end_source": "fixture_audio_end",
        },
        "turn_classification": {
            "cold_turn_index": 1,
            "steady_state_start_turn": 2,
        },
        "log_paths": {
            "live_call": str(ROOT_DIR / "resources" / "logs" / "live-call-streaming.log"),
            "tts": str(ROOT_DIR / "resources" / "logs" / "tts-streaming.log"),
        },
        "turns": [],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    async with aiohttp.ClientSession(timeout=timeout) as http:
        _console_log("HTTP message sent", method="GET", path="/api/health")
        async with http.get(f"{api_url}/api/health") as health:
            _console_log("HTTP response received", method="GET", path="/api/health", status=health.status)
            if health.status >= 400:
                raise RuntimeError(f"Omnix gateway health check failed: HTTP {health.status}")
        session_payload = {"title": f"Live Voice API test {manifest['started_at_utc']}"}
        _console_log("HTTP message sent", method="POST", path="/api/chat/sessions")
        async with http.post(f"{api_url}/api/chat/sessions", json=session_payload) as response:
            _console_log("HTTP response received", method="POST", path="/api/chat/sessions", status=response.status)
            if response.status >= 400:
                body = await response.text()
                raise RuntimeError(f"Could not create API test chat session: HTTP {response.status} {body[:240]}")
            session = await response.json()
        session_id = str(session.get("id") or "")
        if not session_id:
            raise RuntimeError(f"Chat session response did not include an id: {session!r}")

        stt_ws = await websocket_connect(_websocket_url(stt_url, "/ws/transcribe"), open_timeout=20, max_size=8 * 1024 * 1024)
        tts_reporter = DiagnosticReporter(http, api_url, f"live-call:{session_id}:audio-session")
        tts_reporter.record("live_audio_session_created", {"session_id": session_id, "voice_id": voice, "websocket_scope": "live_session"}, "controller")
        tts_ws = await websocket_connect(_websocket_url(api_url, "/api/tts/live-call/websocket"), open_timeout=20, max_size=16 * 1024 * 1024)
        tts_reporter.record("session_websocket_opened", {"websocket_path": "/api/tts/live-call/websocket", "websocket_scope": "live_session"}, "pcm_session")
        tts_client = ApiTtsClient(tts_ws, tts_reporter, voice, session_id)
        stt_reporter = DiagnosticReporter(http, api_url, f"live-call:{session_id}:capture")
        stt_client = ApiSttClient(stt_ws, stt_reporter)
        try:
            await stt_client.negotiate()
            for index, audio_path in enumerate(audio_paths, start=1):
                turn = TurnResult(
                    index=index,
                    audio_file=audio_path.name,
                    input_rate=0,
                    input_samples=0,
                    run_state="cold" if index == 1 else "warm",
                )
                turn_started = time.perf_counter()
                turn_suffix = f"api-{index}-{uuid.uuid4().hex[:10]}"
                reporter = DiagnosticReporter(http, api_url, f"live-call:voice-turn:{turn_suffix}")
                reporter.record("reporter_created", {"session_id": session_id, "turn_index": index}, "controller")
                try:
                    source_rate, source_pcm = _read_pcm16(audio_path)
                    turn.input_rate = source_rate
                    turn.input_samples = len(source_pcm) // 2
                    pcm16 = _resample_pcm16(source_pcm, source_rate, stt_client.sample_rate)
                    reporter.record("stt_audio_input_prepared", {
                        "audio_file": audio_path.name,
                        "input_sample_rate": source_rate,
                        "input_samples": turn.input_samples,
                        "stt_sample_rate": stt_client.sample_rate,
                        "stt_samples": len(pcm16) // 2,
                    }, "live_voice_controller")
                    stt_started_at = time.perf_counter()
                    turn.stt_started_at = stt_started_at
                    transcript = await stt_client.send_turn(pcm16, turn)
                    response_text = await _stream_chat_to_tts(http, api_url, session_id, transcript, turn_suffix, turn, reporter, tts_client)
                    turn.llm_text_chars = len(response_text)
                    if turn.tts_phrase_count <= 0:
                        raise RuntimeError(f"No TTS phrases were synthesized for turn {index}")
                    if turn.tts_sample_rate != TTS_SAMPLE_RATE:
                        raise RuntimeError(f"Live TTS returned {turn.tts_sample_rate} Hz; expected {TTS_SAMPLE_RATE} Hz")
                    metrics = turn.metrics()
                    for metric_name in (
                        "final_to_first_token_ms",
                        "first_token_to_tts_request_ms",
                        "tts_request_to_first_pcm_ms",
                        "first_pcm_to_playback_ms",
                        "final_to_first_playback_ms",
                        "stt_to_first_tts_ms",
                        "stt_to_first_playback_ms",
                        "speech_end_to_final_ms",
                        "speech_end_to_first_tts_ms",
                        "speech_end_to_first_playback_ms",
                    ):
                        metric_value = metrics.get(metric_name)
                        if metric_value is None or metric_value < 0:
                            raise RuntimeError(f"{metric_name} was invalid on turn {index}: {metric_value}")
                    turn.completed = True
                    reporter.record("voice_audio_turnaround", {
                        "turn_index": index,
                        "stt_finalize_ms": turn.stt_finalize_ms,
                        **metrics,
                        "total_turn_ms": metrics["speech_end_to_first_playback_ms"],
                        "pipeline_completion_ms": (time.perf_counter() - turn_started) * 1_000,
                    }, "api_test")
                    manifest["turns"].append(turn.manifest_dict())
                    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                    _console_log("turn completed", turn=index, streaming_tts_overlap=turn.streaming_tts_overlap, final_to_first_playback_ms=turn.final_to_first_playback_ms)
                finally:
                    await reporter.close("turn_finished" if turn.completed else "turn_failed", {"turn_index": index, "completed": turn.completed})

            overlap_turns = sum(1 for turn in manifest["turns"] if turn["streaming_tts_overlap"])
            manifest["streaming_tts_overlap_turns"] = overlap_turns
            manifest["completed_at_utc"] = _utc_now()
            manifest["completed"] = True
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            if overlap_turns == 0:
                raise RuntimeError("No turn started TTS before the LLM stream completed. The API harness is no longer exercising streaming chat-to-TTS overlap.")
            await stt_reporter.close("live_capture_session_closed", {"session_id": session_id})
            await tts_reporter.close("live_audio_session_closed", {"reason": "api_test_complete", "session_id": session_id})
            return manifest
        finally:
            if not stt_reporter.closed:
                try:
                    await stt_reporter.close("live_capture_session_failed", {"session_id": session_id})
                except Exception:
                    pass
            if not tts_reporter.closed:
                try:
                    await tts_reporter.close("live_audio_session_failed", {"reason": "api_test_failed", "session_id": session_id})
                except Exception:
                    pass
            await stt_ws.close()
            await tts_ws.close()
            try:
                _console_log("HTTP message sent", method="DELETE", path=f"/api/chat/sessions/{session_id}")
                async with http.delete(f"{api_url}/api/chat/sessions/{session_id}") as response:
                    await response.read()
                    _console_log("HTTP response received", method="DELETE", path=f"/api/chat/sessions/{session_id}", status=response.status)
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass


@pytest.mark.e2e
@pytest.mark.skipif(not RUN_API_TEST, reason="Set OMNIX_RUN_LIVE_VOICE_API=1 to run the five-turn API test")
def test_five_turn_live_voice_api() -> None:
    """Run five committed voice turns through streaming STT, LLM, and TTS."""

    try:
        manifest = asyncio.run(_run_api_test())
    except Exception as exc:
        pytest.fail(f"Live Voice API test failed: {exc}")
    assert manifest["completed"] is True
    assert len(manifest["turns"]) == 5
    assert all(turn["completed"] for turn in manifest["turns"])
    assert manifest["streaming_tts_overlap_turns"] >= 1
