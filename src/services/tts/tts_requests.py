"""What the TTS service's routes accept."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# One request synthesizes at most this much text (about 25 minutes of speech);
# longer work is split by the caller (audiobook render units, live phrases).
MAX_TTS_TEXT_CHARS = 20_000


class TtsBlendPart(BaseModel):
    speaker: str = Field(min_length=1, max_length=200)
    weight: float = Field(gt=0, le=1)


class TtsGenerateRequest(BaseModel):
    text: str = Field(max_length=MAX_TTS_TEXT_CHARS)
    # The engine the caller expects; empty serves whichever engine is loaded.
    provider: str = ""
    # A pinned caller (a Voice Studio job): refuse with 409 instead of switching.
    require_loaded: bool = False
    speaker: str = "default"
    language: str = "en"
    speed: float = 1.0
    pitch: float = 0.0
    emotion: str = "neutral"
    trace_id: str = ""
    # Sampling overrides (audiobook renders); unknown keys are dropped.
    parameters: dict[str, Any] = Field(default_factory=dict)
    # A voice between library voices (Voice Studio §5): engines with the voice_blend capability only.
    speaker_blend: list[TtsBlendPart] = Field(default_factory=list, max_length=4)


class TtsGenerationParametersRequest(BaseModel):
    parameters: dict[str, Any] = Field(default_factory=dict)
    provider: str = ""


class TtsProviderSelectRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=64)


class TtsGenerateStreamRequest(BaseModel):
    text: str = Field(max_length=MAX_TTS_TEXT_CHARS)
    provider: str = ""
    speaker: str = "default"
    language: str = "en"
    chunk_size: int = 6
    temperature: float = 0.6
    top_k: int = 20
    top_p: float = 0.85
    repetition_penalty: float = 1.0
    append_silence: bool = False
    max_new_tokens: int = 180
    trace_id: str = ""
    # The decode: live speech asks for the CUDA-graph one (parity off); unset keeps the provider's setting.
    parity_mode: bool | None = None


class TtsVoiceCloneRequest(BaseModel):
    voice_id: str
    gender: str = "neutral"
    language: str = "en"
    ref_text: str = ""
