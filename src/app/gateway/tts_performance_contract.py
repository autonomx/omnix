"""Typed live-speech performance intent and provider capability declarations."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SpeechAct = Literal[
    "acknowledgement",
    "answer",
    "question",
    "reassurance",
    "reflection",
    "instruction",
]
DeliveryLevel = Literal["low", "moderate", "high"]
DeliveryPace = Literal["slightly_slow", "natural", "slightly_fast"]
ClausePause = Literal["short", "medium", "long"]


class SpeechOnsetPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    desired_perceived_onset_ms: int = Field(default=450, ge=0, le=2_000)
    maximum_additional_delay_ms: int = Field(default=350, ge=0, le=1_000)


class NonverbalEligibility(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    breath: bool = False
    acknowledgement: bool = False
    amused_exhale: bool = False
    sigh: bool = False


class SpeechPerformancePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    speech_act: SpeechAct = "answer"
    energy: DeliveryLevel = "moderate"
    warmth: DeliveryLevel = "moderate"
    certainty: DeliveryLevel = "moderate"
    pace: DeliveryPace = "natural"
    clause_pause: ClausePause = "medium"
    emphasis: list[str] = Field(default_factory=list, max_length=6)
    onset_policy: SpeechOnsetPolicy = Field(default_factory=SpeechOnsetPolicy)
    nonverbal_eligibility: NonverbalEligibility = Field(default_factory=NonverbalEligibility)


class TtsProviderCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str
    supports_streaming: bool
    supports_concurrent_generation: bool
    supports_emotion: bool
    supports_speaking_rate: bool
    supports_word_emphasis: bool
    supports_ssml: bool
    supports_word_timestamps: bool


FASTER_QWEN3_TTS_CAPABILITIES = TtsProviderCapabilities(
    provider="faster_qwen3_tts",
    supports_streaming=True,
    supports_concurrent_generation=False,
    supports_emotion=False,
    supports_speaking_rate=False,
    supports_word_emphasis=False,
    supports_ssml=False,
    supports_word_timestamps=False,
)


__all__ = [
    "FASTER_QWEN3_TTS_CAPABILITIES",
    "NonverbalEligibility",
    "SpeechOnsetPolicy",
    "SpeechPerformancePlan",
    "TtsProviderCapabilities",
]
