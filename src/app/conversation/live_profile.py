"""Typed Live Conversation behavior contracts shared across features."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PresencePreset = Literal["quiet", "natural", "engaged", "listener"]
ConversationStance = Literal["automatic", "listen", "discuss", "advise", "brainstorm", "teach"]
ConversationPace = Literal["quick", "balanced", "reflective"]
InterruptionPreference = Literal["easy", "balanced", "finish_more"]
AssistantBackchannelMode = Literal["off", "minimal", "natural"]
InitiativeMode = Literal["off", "gentle", "active"]
LongPauseBehavior = Literal["wait", "reassure", "ask_to_continue"]
ResponseLength = Literal["brief", "conversational", "detailed"]
ResponseOnsetStyle = Literal["adaptive", "immediate", "natural", "reflective"]
EmotionalAttunement = Literal["off", "subtle", "expressive"]
TopicContinuity = Literal["focused", "natural", "exploratory"]
DuplexMode = Literal["automatic", "half_duplex", "echo_aware"]
PronunciationSavePolicy = Literal["ask", "session_only", "allow"]
SceneTalkLevel = Literal["rarely", "sometimes", "often"]
SceneTalkAttemptsPerHour = Literal[6, 12, 24, 48]
_CLOCK = r"^(?:[01]\d|2[0-3]):[0-5]\d$"

# Characters talking to each other (companion 6.1): how long a call stays silent before one of them starts, and
# how many talk attempts (lines and starts, each a model call) an account may make an hour.
SCENE_TALK_LEVELS: dict[str, tuple[float, int]] = {
    "rarely": (90.0, 6),
    "sometimes": (45.0, 12),
    "often": (20.0, 24),
}
# These settings are global (Q14): only the account's defaults carry them, whatever a chat overrides.
SCENE_TALK_FIELDS = (
    "scene_talk_enabled",
    "scene_talk_level",
    "scene_talk_attempts_per_hour",
    "scene_talk_max_lines",
    "scene_memory_per_character",
)


class LiveConversationProfile(BaseModel):
    """Validated behavior used by live conversation policy and generation."""

    model_config = ConfigDict(extra="forbid")

    presence_preset: PresencePreset = "natural"
    talkativeness: int = Field(default=50, ge=0, le=100)
    conversation_stance: ConversationStance = "automatic"
    conversation_pace: ConversationPace = "balanced"
    interruption_preference: InterruptionPreference = "balanced"
    assistant_backchannel_mode: AssistantBackchannelMode = "off"
    initiative_mode: InitiativeMode = "gentle"
    idle_threshold_ms: int = Field(default=15_000, ge=5_000, le=120_000)
    long_pause_behavior: LongPauseBehavior = "wait"
    response_length: ResponseLength = "conversational"
    response_onset_style: ResponseOnsetStyle = "adaptive"
    emotional_attunement: EmotionalAttunement = "subtle"
    topic_continuity: TopicContinuity = "natural"
    max_idle_prompts: int = Field(default=1, ge=0, le=3)
    # Social initiative (companion 3.3): no unprompted remark inside quiet hours (local clock, may wrap midnight),
    # and at most this many an hour. A finished task's report is not social and is not held back by either.
    quiet_hours_enabled: bool = False
    quiet_hours_start: str = Field(default="22:00", pattern=_CLOCK)
    quiet_hours_end: str = Field(default="08:00", pattern=_CLOCK)
    max_initiatives_per_hour: int = Field(default=4, ge=0, le=20)
    duplex_mode: DuplexMode = "automatic"
    pronunciation_save_policy: PronunciationSavePolicy = "ask"
    # Characters on one call talk to each other (companion 6), on by default (owner 2026-11-19). A thread is at most
    # scene_talk_max_lines character lines, the reply to the person included; attempts_per_hour None means the
    # level's number.
    scene_talk_enabled: bool = True
    scene_talk_level: SceneTalkLevel = "sometimes"
    scene_talk_attempts_per_hour: SceneTalkAttemptsPerHour | None = None
    scene_talk_max_lines: int = Field(default=6, ge=2, le=10)
    # The most memories about one present character in a prompt.
    scene_memory_per_character: int = Field(default=5, ge=0, le=20)
    profile_version: int = Field(default=1, ge=1)

    def scene_talk_silence_seconds(self) -> float:
        return SCENE_TALK_LEVELS[self.scene_talk_level][0]

    def scene_talk_attempt_cap(self) -> int:
        if self.scene_talk_attempts_per_hour is not None:
            return int(self.scene_talk_attempts_per_hour)
        return SCENE_TALK_LEVELS[self.scene_talk_level][1]


class LiveConversationProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    presence_preset: PresencePreset | None = None
    talkativeness: int | None = Field(default=None, ge=0, le=100)
    conversation_stance: ConversationStance | None = None
    conversation_pace: ConversationPace | None = None
    interruption_preference: InterruptionPreference | None = None
    assistant_backchannel_mode: AssistantBackchannelMode | None = None
    initiative_mode: InitiativeMode | None = None
    idle_threshold_ms: int | None = Field(default=None, ge=5_000, le=120_000)
    long_pause_behavior: LongPauseBehavior | None = None
    response_length: ResponseLength | None = None
    response_onset_style: ResponseOnsetStyle | None = None
    emotional_attunement: EmotionalAttunement | None = None
    topic_continuity: TopicContinuity | None = None
    max_idle_prompts: int | None = Field(default=None, ge=0, le=3)
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = Field(default=None, pattern=_CLOCK)
    quiet_hours_end: str | None = Field(default=None, pattern=_CLOCK)
    max_initiatives_per_hour: int | None = Field(default=None, ge=0, le=20)
    duplex_mode: DuplexMode | None = None
    pronunciation_save_policy: PronunciationSavePolicy | None = None
    # Global (Q14): honoured on the defaults only; a chat's own update drops them. An explicit null for
    # scene_talk_attempts_per_hour goes back to the level's number.
    scene_talk_enabled: bool | None = None
    scene_talk_level: SceneTalkLevel | None = None
    scene_talk_attempts_per_hour: SceneTalkAttemptsPerHour | None = None
    scene_talk_max_lines: int | None = Field(default=None, ge=2, le=10)
    scene_memory_per_character: int | None = Field(default=None, ge=0, le=20)


class LiveConversationProfileEnvelope(BaseModel):
    user_defaults: LiveConversationProfile
    session_override: LiveConversationProfile | None = None
    effective: LiveConversationProfile
    source: Literal["user_defaults", "session_override"]
