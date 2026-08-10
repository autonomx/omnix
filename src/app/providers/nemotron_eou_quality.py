"""Quality-first finalization policy for Nemotron + Parakeet EOU.

Live Nemotron hypotheses stay available for draft UI and endpoint coordination,
but the submitted user transcript is decoded once from the complete buffered
utterance. This prevents a short or fragmented streaming hypothesis from
becoming the authoritative sentence when Parakeet closes the turn.
"""
from __future__ import annotations

import time

from app.providers.nemotron_eou_streaming import NemotronEouModelManager


class QualityFirstNemotronEouModelManager(NemotronEouModelManager):
    """Use full-buffer Nemotron decoding for authoritative finals."""

    def finalize(
        self,
        segment_id: str,
        pcm16le_fallback: bytes = b"",
    ) -> tuple[str, dict[str, float]]:
        stream = self._streams.get(segment_id)
        streaming_text = stream.nemotron.finalize_text() if stream is not None else ""

        if not pcm16le_fallback:
            return streaming_text, {
                "authoritative_full_decode": 0.0,
                "streaming_final": 1.0 if streaming_text else 0.0,
                "offline_fallback": 0.0,
                "streaming_chars": float(len(streaming_text)),
                "authoritative_chars": float(len(streaming_text)),
                "authoritative_changed": 0.0,
            }

        started = time.perf_counter()
        try:
            authoritative_text = self.transcribe_pcm16(pcm16le_fallback).strip()
        except Exception:
            if not streaming_text:
                raise
            return streaming_text, {
                "authoritative_full_decode": 0.0,
                "full_decode_failed": 1.0,
                "streaming_final": 1.0,
                "offline_fallback": 0.0,
                "streaming_chars": float(len(streaming_text)),
                "authoritative_chars": float(len(streaming_text)),
                "authoritative_changed": 0.0,
            }

        full_decode_ms = (time.perf_counter() - started) * 1000.0
        if authoritative_text:
            return authoritative_text, {
                "authoritative_full_decode": 1.0,
                "full_decode_ms": round(full_decode_ms, 3),
                "streaming_final": 0.0,
                "offline_fallback": 0.0,
                "streaming_chars": float(len(streaming_text)),
                "authoritative_chars": float(len(authoritative_text)),
                "authoritative_changed": 1.0 if authoritative_text != streaming_text else 0.0,
            }

        return streaming_text, {
            "authoritative_full_decode": 0.0,
            "full_decode_empty": 1.0,
            "full_decode_ms": round(full_decode_ms, 3),
            "streaming_final": 1.0 if streaming_text else 0.0,
            "offline_fallback": 0.0,
            "streaming_chars": float(len(streaming_text)),
            "authoritative_chars": float(len(streaming_text)),
            "authoritative_changed": 0.0,
        }


quality_model_manager = QualityFirstNemotronEouModelManager()
