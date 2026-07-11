"""Server-owned Live Chat presence profiles with user defaults and session overrides."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
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


class LiveConversationProfile(BaseModel):
    """Validated behavior used by Live Chat policy and generation."""

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
    duplex_mode: DuplexMode = "automatic"
    pronunciation_save_policy: PronunciationSavePolicy = "ask"
    profile_version: int = Field(default=1, ge=1)


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
    duplex_mode: DuplexMode | None = None
    pronunciation_save_policy: PronunciationSavePolicy | None = None


class LiveConversationProfileEnvelope(BaseModel):
    user_defaults: LiveConversationProfile
    session_override: LiveConversationProfile | None = None
    effective: LiveConversationProfile
    source: Literal["user_defaults", "session_override"]


def default_live_conversation_profile_path() -> Path:
    configured = os.getenv("OMNIX_LIVE_CONVERSATION_PROFILE_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path("resources/data/live_conversation_profiles.json")


class LiveConversationProfileStore:
    """Small atomic JSON store; guarded for concurrent local gateway requests."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_live_conversation_profile_path()
        self._lock = threading.RLock()

    def get_defaults(self) -> LiveConversationProfile:
        with self._lock:
            payload = self._read()
            return LiveConversationProfile.model_validate(payload.get("defaults") or {})

    def update_defaults(self, update: LiveConversationProfileUpdate) -> LiveConversationProfile:
        with self._lock:
            payload = self._read()
            current = LiveConversationProfile.model_validate(payload.get("defaults") or {})
            next_profile = self._merge(current, update)
            payload["defaults"] = next_profile.model_dump(mode="json")
            self._write(payload)
            return next_profile

    def get(self, session_id: str) -> LiveConversationProfileEnvelope:
        with self._lock:
            payload = self._read()
            defaults = LiveConversationProfile.model_validate(payload.get("defaults") or {})
            raw_override = (payload.get("sessions") or {}).get(session_id)
            override = LiveConversationProfile.model_validate(raw_override) if raw_override else None
            return LiveConversationProfileEnvelope(
                user_defaults=defaults,
                session_override=override,
                effective=override or defaults,
                source="session_override" if override else "user_defaults",
            )

    def update(self, session_id: str, update: LiveConversationProfileUpdate) -> LiveConversationProfileEnvelope:
        with self._lock:
            payload = self._read()
            defaults = LiveConversationProfile.model_validate(payload.get("defaults") or {})
            sessions = payload.setdefault("sessions", {})
            current = LiveConversationProfile.model_validate(sessions.get(session_id) or defaults.model_dump(mode="json"))
            next_profile = self._merge(current, update)
            sessions[session_id] = next_profile.model_dump(mode="json")
            self._write(payload)
            return LiveConversationProfileEnvelope(
                user_defaults=defaults,
                session_override=next_profile,
                effective=next_profile,
                source="session_override",
            )

    def clear(self, session_id: str) -> LiveConversationProfileEnvelope:
        with self._lock:
            payload = self._read()
            sessions = payload.setdefault("sessions", {})
            sessions.pop(session_id, None)
            self._write(payload)
            defaults = LiveConversationProfile.model_validate(payload.get("defaults") or {})
            return LiveConversationProfileEnvelope(
                user_defaults=defaults,
                session_override=None,
                effective=defaults,
                source="user_defaults",
            )

    @staticmethod
    def _merge(current: LiveConversationProfile, update: LiveConversationProfileUpdate) -> LiveConversationProfile:
        patch = update.model_dump(exclude_none=True)
        data = current.model_dump(mode="json")
        data.update(patch)
        data["profile_version"] = current.profile_version + 1
        return LiveConversationProfile.model_validate(data)

    def _read(self) -> dict:
        if not self.path.is_file():
            return {"format_version": 1, "defaults": {}, "sessions": {}}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"format_version": 1, "defaults": {}, "sessions": {}}
        if not isinstance(payload, dict):
            return {"format_version": 1, "defaults": {}, "sessions": {}}
        payload.setdefault("format_version", 1)
        payload.setdefault("defaults", {})
        payload.setdefault("sessions", {})
        return payload

    def _write(self, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)


_default_store: LiveConversationProfileStore | None = None
_default_store_path: Path | None = None


def default_live_conversation_profile_store() -> LiveConversationProfileStore:
    global _default_store, _default_store_path
    path = default_live_conversation_profile_path()
    if _default_store is None or _default_store_path != path:
        _default_store = LiveConversationProfileStore(path)
        _default_store_path = path
    return _default_store


__all__ = [
    "LiveConversationProfile",
    "LiveConversationProfileEnvelope",
    "LiveConversationProfileStore",
    "LiveConversationProfileUpdate",
    "default_live_conversation_profile_path",
    "default_live_conversation_profile_store",
]
