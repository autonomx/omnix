"""Quality-first finalization policy for Nemotron + Parakeet EOU.

Live Nemotron hypotheses stay available for draft UI and endpoint coordination,
but the submitted user transcript is decoded once from the complete buffered
utterance. This prevents a short or fragmented streaming hypothesis from
becoming the authoritative sentence when Parakeet closes the turn.
"""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Any

from app.providers.nemotron_eou_streaming import (
    NemotronEouModelManager,
    _configure_streaming_context,
    _metric,
    env_int,
)

_SUPPORTED_FINAL_RIGHT_CONTEXTS = {0, 1, 6, 13}
_DEFAULT_PREDECODE_DELAY_MS = 300
_DEFAULT_PREDECODE_TAIL_PEAK = 96


@dataclass(frozen=True)
class _QualityPredecode:
    authoritative_text: str
    streaming_text: str
    audio_bytes: int
    audio_digest: bytes
    decode_ms: float


def _pcm16_peak_abs(pcm16le: bytes) -> int:
    """Return a conservative peak amplitude for little-endian PCM16."""
    if len(pcm16le) % 2:
        return 32_767
    peak = 0
    for offset in range(0, len(pcm16le), 2):
        sample = int.from_bytes(
            pcm16le[offset : offset + 2],
            byteorder="little",
            signed=True,
        )
        peak = max(peak, abs(sample))
    return peak


class QualityFirstNemotronEouModelManager(NemotronEouModelManager):
    """Use a higher-context full-buffer Nemotron decode for authoritative finals."""

    def __init__(self) -> None:
        super().__init__()
        # Keep the live stream at the low-latency right context (normally 1 =
        # 160 ms), but decode the completed utterance with Nemotron's largest
        # supported right context by default. The shared model is reconfigured
        # only while holding the Nemotron lock, so this adds no duplicate model
        # or VRAM allocation and cannot race a streaming feed.
        requested = env_int("OMNIX_NEMOTRON_FINAL_RIGHT_CONTEXT", 13)
        self.nemotron_final_right_context = (
            requested if requested in _SUPPORTED_FINAL_RIGHT_CONTEXTS else 13
        )
        # A Parakeet EOU candidate usually arrives hundreds of milliseconds
        # before the browser commits its endpoint. Use a short quiet-period delay
        # to move the expensive authoritative decode into that already-existing
        # endpoint window. Reuse remains fail-closed: any changed transcript,
        # changed PCM prefix, or non-trivial tail energy forces the normal final
        # full-buffer decode.
        self.predecode_delay_ms = max(
            0,
            env_int("OMNIX_NEMOTRON_PREDECODE_DELAY_MS", _DEFAULT_PREDECODE_DELAY_MS),
        )
        self.predecode_tail_peak = max(
            0,
            env_int("OMNIX_NEMOTRON_PREDECODE_TAIL_PEAK", _DEFAULT_PREDECODE_TAIL_PEAK),
        )
        self._predecode_state_lock = threading.RLock()
        self._quality_audio: dict[str, bytearray] = {}
        self._predecode_cache: dict[str, _QualityPredecode] = {}
        self._predecode_timers: dict[str, threading.Timer] = {}

    def health_details(self) -> dict[str, Any]:
        return {
            **super().health_details(),
            "nemotron_final_right_context": self.nemotron_final_right_context,
            "nemotron_predecode_delay_ms": self.predecode_delay_ms,
            "nemotron_predecode_tail_peak": self.predecode_tail_peak,
        }

    def _transcribe_quality_pcm16(self, pcm16le: bytes) -> str:
        # Unit tests commonly replace transcribe_pcm16 without loading NeMo.
        # Production finalization always has a loaded model because the segment
        # has already streamed through Nemotron.
        if self.nemotron_model is None:
            return self.transcribe_pcm16(pcm16le)

        with self._nemotron_lock:
            _configure_streaming_context(self.nemotron_model, self.nemotron_final_right_context)
            try:
                return self.transcribe_pcm16(pcm16le)
            finally:
                # Restore the live configuration before the next microphone
                # chunk can enter the shared Nemotron model.
                _configure_streaming_context(self.nemotron_model, self.nemotron_right_context)

    def feed(self, segment_id: str, pcm16le: bytes):
        # Keep the quality snapshot byte-for-byte aligned with the Nemotron
        # streaming state. The lock is re-entrant because the base feed already
        # protects Nemotron inference with the same RLock.
        with self._nemotron_lock:
            update = super().feed(segment_id, pcm16le)
            with self._predecode_state_lock:
                self._quality_audio.setdefault(segment_id, bytearray()).extend(pcm16le)
                cached = self._predecode_cache.get(segment_id)
                if cached is not None and cached.streaming_text != update.transcript:
                    self._predecode_cache.pop(segment_id, None)
        if update.eou:
            self._schedule_predecode(segment_id)
        return update

    def _schedule_predecode(self, segment_id: str) -> None:
        with self._predecode_state_lock:
            if segment_id in self._predecode_cache:
                return
            existing = self._predecode_timers.get(segment_id)
            if existing is not None and existing.is_alive():
                return
            timer = threading.Timer(
                self.predecode_delay_ms / 1000.0,
                self._run_predecode,
                args=(segment_id,),
            )
            timer.daemon = True
            self._predecode_timers[segment_id] = timer
            timer.start()
        _metric(
            "stt_authoritative_predecode_scheduled",
            segment_id=segment_id,
            delay_ms=self.predecode_delay_ms,
            final_right_context=self.nemotron_final_right_context,
        )

    def _run_predecode(self, segment_id: str) -> None:
        try:
            with self._nemotron_lock:
                stream = self._streams.get(segment_id)
                if stream is None:
                    return
                streaming_text = stream.nemotron.finalize_text()
                if not streaming_text:
                    return
                with self._predecode_state_lock:
                    audio = bytes(self._quality_audio.get(segment_id, b""))
                if not audio:
                    return
                started = time.perf_counter()
                try:
                    authoritative_text = self._transcribe_quality_pcm16(audio).strip()
                except Exception as exc:
                    _metric(
                        "stt_authoritative_predecode_failed",
                        segment_id=segment_id,
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
                    return
                decode_ms = (time.perf_counter() - started) * 1000.0
                if not authoritative_text:
                    return
                cache = _QualityPredecode(
                    authoritative_text=authoritative_text,
                    streaming_text=streaming_text,
                    audio_bytes=len(audio),
                    audio_digest=hashlib.blake2s(audio, digest_size=16).digest(),
                    decode_ms=decode_ms,
                )
                with self._predecode_state_lock:
                    if segment_id not in self._streams:
                        return
                    self._predecode_cache[segment_id] = cache
                _metric(
                    "stt_authoritative_predecode_completed",
                    segment_id=segment_id,
                    audio_bytes=len(audio),
                    streaming_chars=len(streaming_text),
                    authoritative_chars=len(authoritative_text),
                    authoritative_changed=authoritative_text != streaming_text,
                    decode_ms=round(decode_ms, 3),
                    final_right_context=self.nemotron_final_right_context,
                )
        finally:
            with self._predecode_state_lock:
                current = self._predecode_timers.get(segment_id)
                if current is threading.current_thread():
                    self._predecode_timers.pop(segment_id, None)

    def _cancel_pending_predecode(self, segment_id: str) -> None:
        with self._predecode_state_lock:
            timer = self._predecode_timers.pop(segment_id, None)
        if timer is not None:
            timer.cancel()

    def _reusable_predecode(
        self,
        segment_id: str,
        pcm16le_fallback: bytes,
        streaming_text: str,
    ) -> tuple[_QualityPredecode | None, int]:
        with self._predecode_state_lock:
            cached = self._predecode_cache.get(segment_id)
        if cached is None or cached.streaming_text != streaming_text:
            return None, 32_767
        if cached.audio_bytes > len(pcm16le_fallback):
            return None, 32_767
        prefix = pcm16le_fallback[: cached.audio_bytes]
        if hashlib.blake2s(prefix, digest_size=16).digest() != cached.audio_digest:
            return None, 32_767
        tail = pcm16le_fallback[cached.audio_bytes :]
        tail_peak = _pcm16_peak_abs(tail)
        if tail_peak > self.predecode_tail_peak:
            return None, tail_peak
        return cached, tail_peak

    def finalize(
        self,
        segment_id: str,
        pcm16le_fallback: bytes = b"",
    ) -> tuple[str, dict[str, float]]:
        self._cancel_pending_predecode(segment_id)
        final_context = float(self.nemotron_final_right_context)

        # If a predecode is already running, acquiring this lock waits for that
        # work to finish once instead of racing it with a duplicate final decode.
        with self._nemotron_lock:
            stream = self._streams.get(segment_id)
            streaming_text = stream.nemotron.finalize_text() if stream is not None else ""

            if not pcm16le_fallback:
                return streaming_text, {
                    "authoritative_full_decode": 0.0,
                    "authoritative_predecode_reused": 0.0,
                    "streaming_final": 1.0 if streaming_text else 0.0,
                    "offline_fallback": 0.0,
                    "streaming_chars": float(len(streaming_text)),
                    "authoritative_chars": float(len(streaming_text)),
                    "authoritative_changed": 0.0,
                    "final_right_context": final_context,
                }

            cached, tail_peak = self._reusable_predecode(
                segment_id,
                pcm16le_fallback,
                streaming_text,
            )
            if cached is not None:
                _metric(
                    "stt_authoritative_predecode_reused",
                    segment_id=segment_id,
                    decode_ms=round(cached.decode_ms, 3),
                    tail_bytes=len(pcm16le_fallback) - cached.audio_bytes,
                    tail_peak=tail_peak,
                    final_right_context=self.nemotron_final_right_context,
                )
                return cached.authoritative_text, {
                    "authoritative_full_decode": 1.0,
                    "authoritative_predecode_reused": 1.0,
                    "full_decode_ms": round(cached.decode_ms, 3),
                    "streaming_final": 0.0,
                    "offline_fallback": 0.0,
                    "streaming_chars": float(len(streaming_text)),
                    "authoritative_chars": float(len(cached.authoritative_text)),
                    "authoritative_changed": (
                        1.0 if cached.authoritative_text != streaming_text else 0.0
                    ),
                    "predecode_tail_peak": float(tail_peak),
                    "final_right_context": final_context,
                }

            started = time.perf_counter()
            try:
                authoritative_text = self._transcribe_quality_pcm16(pcm16le_fallback).strip()
            except Exception:
                if not streaming_text:
                    raise
                return streaming_text, {
                    "authoritative_full_decode": 0.0,
                    "authoritative_predecode_reused": 0.0,
                    "full_decode_failed": 1.0,
                    "streaming_final": 1.0,
                    "offline_fallback": 0.0,
                    "streaming_chars": float(len(streaming_text)),
                    "authoritative_chars": float(len(streaming_text)),
                    "authoritative_changed": 0.0,
                    "final_right_context": final_context,
                }

            full_decode_ms = (time.perf_counter() - started) * 1000.0
            if authoritative_text:
                return authoritative_text, {
                    "authoritative_full_decode": 1.0,
                    "authoritative_predecode_reused": 0.0,
                    "full_decode_ms": round(full_decode_ms, 3),
                    "streaming_final": 0.0,
                    "offline_fallback": 0.0,
                    "streaming_chars": float(len(streaming_text)),
                    "authoritative_chars": float(len(authoritative_text)),
                    "authoritative_changed": (
                        1.0 if authoritative_text != streaming_text else 0.0
                    ),
                    "predecode_tail_peak": float(tail_peak),
                    "final_right_context": final_context,
                }

            return streaming_text, {
                "authoritative_full_decode": 0.0,
                "authoritative_predecode_reused": 0.0,
                "full_decode_empty": 1.0,
                "full_decode_ms": round(full_decode_ms, 3),
                "streaming_final": 1.0 if streaming_text else 0.0,
                "offline_fallback": 0.0,
                "streaming_chars": float(len(streaming_text)),
                "authoritative_chars": float(len(streaming_text)),
                "authoritative_changed": 0.0,
                "predecode_tail_peak": float(tail_peak),
                "final_right_context": final_context,
            }

    def release(self, segment_id: str) -> None:
        self._cancel_pending_predecode(segment_id)
        with self._nemotron_lock:
            with self._predecode_state_lock:
                self._quality_audio.pop(segment_id, None)
                self._predecode_cache.pop(segment_id, None)
            super().release(segment_id)


quality_model_manager = QualityFirstNemotronEouModelManager()
