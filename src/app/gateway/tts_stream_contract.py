"""Transport-neutral request policy and PCM helpers for TTS streaming."""
from __future__ import annotations

from typing import Any, Iterator

from pydantic import BaseModel, Field, model_validator

from app.shared import remove_emojis

DEFAULT_SAMPLE_RATE = 24_000
STREAM_OUTPUT_BLOCK_SAMPLES = 2_048
STREAM_INITIAL_SILENCE_THRESHOLD = 0.01
STREAM_INITIAL_PREROLL_MS = 40.0
CHAT_STREAM_MIN_NEW_TOKENS = 96
CHAT_STREAM_MAX_NEW_TOKENS = 1_024
CHAT_STREAM_TOKEN_NUMERATOR = 9
CHAT_STREAM_TOKEN_DENOMINATOR = 8
CHAT_STREAM_TOKEN_OVERHEAD = 24
CHAT_STREAM_MIN_REPETITION_PENALTY = 1.05


def estimate_chat_stream_max_new_tokens(text: str) -> int:
    """Bound chat speech while leaving headroom above normal English speech duration."""
    normalized = remove_emojis(text or "").strip()
    estimated = (
        (len(normalized) * CHAT_STREAM_TOKEN_NUMERATOR + CHAT_STREAM_TOKEN_DENOMINATOR - 1)
        // CHAT_STREAM_TOKEN_DENOMINATOR
        + CHAT_STREAM_TOKEN_OVERHEAD
    )
    return max(CHAT_STREAM_MIN_NEW_TOKENS, min(CHAT_STREAM_MAX_NEW_TOKENS, estimated))


class TtsStreamRequest(BaseModel):
    """Browser-facing TTS streaming request shared by binary transports."""

    text: str = ""
    speaker: str | None = None
    language: str | None = "en"
    chunk_size: int = Field(default=12, ge=1, le=256)
    temperature: float = Field(default=0.9, ge=0.0, le=2.0)
    top_k: int = Field(default=50, ge=0)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    repetition_penalty: float = Field(default=1.05, ge=0.0)
    append_silence: bool = True
    max_new_tokens: int | None = Field(default=None, ge=1)
    non_streaming_mode: bool | None = None
    parity_mode: bool | None = None
    request_id: str | None = None
    diagnostics_stream_id: str | None = None

    @model_validator(mode="after")
    def apply_chat_stream_runtime_policy(self) -> "TtsStreamRequest":
        """Use bounded CUDA-graph chat decoding with safe provider fallback on graph failures."""
        stream_id = (self.diagnostics_stream_id or "").strip()
        if not stream_id.startswith("chat-"):
            return self
        self.parity_mode = False
        token_budget = estimate_chat_stream_max_new_tokens(self.text)
        if self.max_new_tokens is None or self.max_new_tokens > token_budget:
            self.max_new_tokens = token_budget
        self.repetition_penalty = max(
            self.repetition_penalty,
            CHAT_STREAM_MIN_REPETITION_PENALTY,
        )
        return self


def stream_pcm16_blocks(
    chunks: Iterator[tuple[bytes, int, Any]],
    *,
    block_samples: int = STREAM_OUTPUT_BLOCK_SAMPLES,
    silence_threshold: float = STREAM_INITIAL_SILENCE_THRESHOLD,
    preroll_ms: float = STREAM_INITIAL_PREROLL_MS,
) -> Iterator[tuple[bytes, int, Any]]:
    """Repack provider chunks into steady PCM16 blocks without altering joins."""
    block_bytes = max(1, int(block_samples)) * 2
    leftover = b""
    leftover_rate = DEFAULT_SAMPLE_RATE
    leftover_timing: Any = {}
    found_speech = False

    for pcm_bytes, sample_rate, timing in chunks:
        sample_rate = int(sample_rate or DEFAULT_SAMPLE_RATE)
        pcm_bytes = even_pcm16_bytes(pcm_bytes)
        if not pcm_bytes:
            continue

        if leftover and sample_rate != leftover_rate:
            yield pad_pcm16_block(leftover, block_bytes), leftover_rate, leftover_timing
            leftover = b""

        if not found_speech:
            start_byte = initial_speech_start_byte(
                pcm_bytes,
                sample_rate,
                silence_threshold,
                preroll_ms,
            )
            if start_byte is None:
                continue
            pcm_bytes = pcm_bytes[start_byte:]
            found_speech = True

        audio = leftover + pcm_bytes
        full_bytes = (len(audio) // block_bytes) * block_bytes
        for offset in range(0, full_bytes, block_bytes):
            yield audio[offset : offset + block_bytes], sample_rate, timing

        leftover = audio[full_bytes:]
        leftover_rate = sample_rate
        leftover_timing = timing

    if leftover:
        yield pad_pcm16_block(leftover, block_bytes), leftover_rate, leftover_timing


def audio_chunk_to_pcm16_bytes(audio_chunk: Any) -> bytes:
    """Convert float-like mono chunks to little-endian PCM16 without numpy."""
    if audio_chunk is None:
        return b""
    if isinstance(audio_chunk, bytes):
        return audio_chunk
    if isinstance(audio_chunk, bytearray):
        return bytes(audio_chunk)

    values = audio_chunk.tolist() if hasattr(audio_chunk, "tolist") else audio_chunk
    if not isinstance(values, (list, tuple)):
        values = [values]

    pcm = bytearray()
    for value in values:
        if isinstance(value, (list, tuple)):
            value = value[0] if value else 0.0
        try:
            sample = float(value)
        except (TypeError, ValueError):
            continue
        sample = max(-1.0, min(1.0, sample))
        pcm.extend(int(sample * 32767).to_bytes(2, byteorder="little", signed=True))
    return bytes(pcm)


def even_pcm16_bytes(pcm_bytes: bytes) -> bytes:
    return pcm_bytes if len(pcm_bytes) % 2 == 0 else pcm_bytes[:-1]


def initial_speech_start_byte(
    pcm_bytes: bytes,
    sample_rate: int,
    silence_threshold: float,
    preroll_ms: float,
) -> int | None:
    threshold = int(32768 * max(0.0, silence_threshold))
    preroll_samples = max(0, int(sample_rate * max(0.0, preroll_ms) / 1000.0))
    for index in range(0, len(pcm_bytes), 2):
        sample = int.from_bytes(pcm_bytes[index : index + 2], "little", signed=True)
        if abs(sample) > threshold:
            start_sample = max(0, index // 2 - preroll_samples)
            return start_sample * 2
    return None


def pad_pcm16_block(pcm_bytes: bytes, block_bytes: int) -> bytes:
    if len(pcm_bytes) >= block_bytes:
        return pcm_bytes
    return pcm_bytes + (b"\x00" * (block_bytes - len(pcm_bytes)))
