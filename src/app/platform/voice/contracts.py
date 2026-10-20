"""The speech capability's contract (ADR-0016, PA-3.3): STT and TTS session ports.

Voice, live voice and live speech build on these. A module imports speech
types from here, never from another speech module's internals. The wire
format of TTS streaming (request policy, PCM framing) is transport-neutral
and lives in the kernel, ``app.conversation.tts_stream_contract``.

- STT session: a ``StreamingTranscriber`` takes PCM as it arrives and yields
  partial and final ``TranscriptUpdate``s.
- TTS session: a ``StreamingSpeechSynthesizer`` turns text into ``AudioDelta``
  frames; live voice streams from a ``TTSProvider`` through a ``TTSLane``.
"""
from __future__ import annotations

import base64
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .assembly import (
        ASSEMBLY_VERSION,
        AssembledChapter,
        AudioSpan,
        PausePolicy,
        TimelineEntry,
        active_energy,
        assemble_chapter,
        normalization_gains,
    )
    from .audio_service import AudioServiceClient, AudioServiceUnavailable, AudioToolRequestError
    from .client_tools import VOICE_CLIENT_TOOLS, VoiceClientTool
    from .jobs import clone_voice, wait_for_engine
    from .loudness import integrated_loudness, normalize_loudness
    from .output_settings import NEUTRAL, sampling_overrides, time_stretch
    from .transcription import transcribe_timed_audio
    from .transcripts import TranscriptDocument, export_transcript, speaker_sample_spans
    from .watermarking import mark as watermark_render


@dataclass
class TranscriptUpdate:
    text: str
    final: bool = False
    confidence: float | None = None
    duration_ms: int | None = None


class StreamingTranscriber:
    """Interface for partial/final realtime transcript producers."""

    def accept_audio(self, pcm: bytes) -> list[TranscriptUpdate]:
        raise NotImplementedError

    def finalize(self) -> TranscriptUpdate:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError


@dataclass
class AudioDelta:
    pcm: bytes
    sample_rate: int = 24000
    sequence: int = 0

    def b64(self) -> str:
        return base64.b64encode(self.pcm).decode("ascii")


class StreamingSpeechSynthesizer:
    def synthesize(self, text: str, *, voice: str = "default", generation: int = 0) -> list[AudioDelta]:
        raise NotImplementedError


class TTSProvider(Protocol):
    provider_name: str

    def generate_audio_stream(
        self,
        *,
        text: str,
        speaker: str | None,
        language: str,
        **kwargs: Any,
    ) -> Iterator[tuple[Any, int, Any]]: ...


class TTSProviderResolver(Protocol):
    def get(self, provider_name: str | None = None) -> TTSProvider | None: ...


class TTSLane(Protocol):
    def stream(
        self,
        provider: TTSProvider,
        *,
        text: str,
        speaker: str | None,
        language: str,
        kwargs: dict[str, Any],
        priority: Any,
        **options: Any,
    ) -> Iterator[tuple[Any, int, Any]]: ...


# Voice output tuning (``output_settings``) that apps apply to their own synthesis
# requests. Loaded on first use, so importing this contract does not load numpy.
_OUTPUT_SETTINGS = frozenset({"NEUTRAL", "sampling_overrides"})
# Voice Studio's tools other modules build on (dubbing): transcripts, timed transcription,
# audio tools, time-stretch, loudness, library voices and render watermarking.
_TOOLS = {
    "TranscriptDocument": ("transcripts", "TranscriptDocument"),
    "export_transcript": ("transcripts", "export_transcript"),
    "speaker_sample_spans": ("transcripts", "speaker_sample_spans"),
    "transcribe_timed_audio": ("transcription", "transcribe_timed_audio"),
    "AudioServiceClient": ("audio_service", "AudioServiceClient"),
    "AudioServiceUnavailable": ("audio_service", "AudioServiceUnavailable"),
    "AudioToolRequestError": ("audio_service", "AudioToolRequestError"),
    "time_stretch": ("output_settings", "time_stretch"),
    "integrated_loudness": ("loudness", "integrated_loudness"),
    "normalize_loudness": ("loudness", "normalize_loudness"),
    "clone_voice": ("jobs", "clone_voice"),
    "wait_for_engine": ("jobs", "wait_for_engine"),
    "watermark_render": ("watermarking", "mark"),
    # The tool port API clients and MCP call (Phase 7); apps register their tools through it.
    "VOICE_CLIENT_TOOLS": ("client_tools", "VOICE_CLIENT_TOOLS"),
    "VoiceClientTool": ("client_tools", "VoiceClientTool"),
}
# Speech assembly (pauses and per-speaker loudness) shared by Voice Studio and apps.
_ASSEMBLY = frozenset({
    "ASSEMBLY_VERSION", "AssembledChapter", "AudioSpan", "PausePolicy", "TimelineEntry",
    "active_energy", "assemble_chapter", "normalization_gains",
})


def __getattr__(name: str) -> Any:
    if name in _OUTPUT_SETTINGS:
        from . import output_settings

        return getattr(output_settings, name)
    if name in _ASSEMBLY:
        from . import assembly

        return getattr(assembly, name)
    if name in _TOOLS:
        import importlib

        module, attribute = _TOOLS[name]
        return getattr(importlib.import_module(f"{__package__}.{module}"), attribute)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ASSEMBLY_VERSION",
    "NEUTRAL",
    "AssembledChapter",
    "AudioDelta",
    "AudioSpan",
    "PausePolicy",
    "TimelineEntry",
    "active_energy",
    "assemble_chapter",
    "normalization_gains",
    "StreamingSpeechSynthesizer",
    "StreamingTranscriber",
    "TTSLane",
    "TTSProvider",
    "TTSProviderResolver",
    "TranscriptUpdate",
    "sampling_overrides",
    "AudioServiceClient",
    "AudioServiceUnavailable",
    "AudioToolRequestError",
    "TranscriptDocument",
    "VOICE_CLIENT_TOOLS",
    "VoiceClientTool",
    "clone_voice",
    "export_transcript",
    "integrated_loudness",
    "normalize_loudness",
    "speaker_sample_spans",
    "time_stretch",
    "transcribe_timed_audio",
    "wait_for_engine",
    "watermark_render",
]
