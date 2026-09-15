"""Conservative Desktop Companion -> Memory v2 evidence bridge.

Only high-confidence, high-importance observations from an explicitly memory-enabled
persistent Chat are retained. Raw frames and raw visible screen text are never stored.
The observation remains external/untrusted evidence so consolidation cannot silently
upgrade screen content into user-asserted truth.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from app.assistant_memory.scope import resolve_session_memory_scope
from app.assistant_memory_v2.contracts import (
    MemorySpaceKey,
    ObservationProvenance,
    VisibilityScope,
)
from app.assistant_memory_v2.observation_store import ObservationAppendRequest
from app.assistant_memory_v2.runtime import (
    AuthoritativeIngestSequenceError,
    PostgresMemoryV2Runtime,
)
from app.chat import default_chat_store

from .models import DesktopObservation
from .observation import screen_prompt_injection_observed

MemoryBridgeStatus = Literal["recorded", "skipped", "error"]

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_URL = re.compile(r"https?://\S+", re.I)
_LONG_NUMBER = re.compile(r"(?<!\d)\d{6,}(?!\d)")
_TOKENISH = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")


@dataclass(frozen=True, slots=True)
class DesktopMemoryBridgeOutcome:
    status: MemoryBridgeStatus
    reason: str
    memory_observation_id: str | None = None


class DesktopCompanionMemoryBridge:
    """Append bounded desktop evidence without delaying the interactive response path."""

    def __init__(
        self,
        *,
        chat_store_factory: Callable[[], Any] = default_chat_store,
        memory_runtime_factory: Callable[[], Any] = PostgresMemoryV2Runtime,
        minimum_importance: float = 0.72,
        minimum_confidence: float = 0.70,
        sequence_retries: int = 4,
    ) -> None:
        self._chat_store_factory = chat_store_factory
        self._memory_runtime_factory = memory_runtime_factory
        self._minimum_importance = minimum_importance
        self._minimum_confidence = minimum_confidence
        self._sequence_retries = max(1, sequence_retries)

    def record(self, observation: DesktopObservation) -> DesktopMemoryBridgeOutcome:
        try:
            session = self._chat_store_factory().get_session(observation.session_id)
        except Exception as exc:
            return DesktopMemoryBridgeOutcome("error", f"chat_store_unavailable:{type(exc).__name__}")
        if session is None:
            return DesktopMemoryBridgeOutcome("skipped", "session_not_found")

        reason = self._eligibility_reason(observation, session)
        if reason is not None:
            return DesktopMemoryBridgeOutcome("skipped", reason)

        try:
            runtime = self._memory_runtime_factory()
            authority = runtime.current()
            if authority.epoch.authority != "v2":
                return DesktopMemoryBridgeOutcome("skipped", "memory_v2_not_authoritative")
            context = resolve_session_memory_scope(session)
            space = MemorySpaceKey(
                principal_id=context.profile_id,
                owner_type=context.owner_type,
                owner_id=context.owner_id,
            )
            visibility = (
                VisibilityScope(kind="project", scope_id=context.project_id)
                if context.project_id
                else VisibilityScope(kind="session", scope_id=context.session_id)
            )
            provider = observation.diagnostics.get("model")
            provenance = ObservationProvenance(
                source_type="external",
                source_id=f"desktop-companion:{observation.source_fingerprint}"[:240],
                trust_level="external_untrusted",
                session_id=observation.session_id,
                model_id=str(provider)[:200] if provider else None,
            )
            request = ObservationAppendRequest(
                space=space,
                visibility_scope=visibility,
                event_type="external_observed",
                occurred_at=observation.observed_at,
                provenance=provenance,
                idempotency_key=f"desktop-companion:{observation.observation_id}"[:240],
                payload=_memory_payload(observation),
                sensitivity="normal",
                correlation_id=observation.observation_id,
                schema_version="desktop-companion-memory@1",
            )
            stored = self._append_authoritative(runtime, request, space)
            return DesktopMemoryBridgeOutcome(
                "recorded",
                "salient_desktop_observation_recorded",
                memory_observation_id=stored.observation_id,
            )
        except Exception as exc:
            return DesktopMemoryBridgeOutcome("error", f"memory_bridge_failed:{type(exc).__name__}")

    def _append_authoritative(
        self,
        runtime: Any,
        request: ObservationAppendRequest,
        space: MemorySpaceKey,
    ) -> Any:
        """Use the exact-sequence authority boundary and retry only sequence races.

        The database still enforces synchronized event/observation watermarks. Reading
        the next candidate sequence outside the write transaction is safe because a
        competing writer can only make this call fail closed; the next iteration then
        observes the advanced authoritative watermark.
        """

        last_error: Exception | None = None
        for _ in range(self._sequence_retries):
            next_sequence = runtime.authority_store.authoritative_event_watermark(space) + 1
            try:
                return runtime.append_authoritative(
                    request,
                    authoritative_event_sequence=next_sequence,
                )
            except AuthoritativeIngestSequenceError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("memory v2 authoritative append exhausted without an attempt")

    def _eligibility_reason(self, observation: DesktopObservation, session: Any) -> str | None:
        if getattr(session, "transcript_policy", "persistent") != "persistent":
            return "private_or_temporary_session"
        if getattr(session, "interaction_mode", "system") == "character":
            if not bool(getattr(session, "write_memory", False)):
                return "character_memory_write_disabled"
            authoritative_character = str(getattr(session, "character_id", "") or "").strip() or None
            if authoritative_character and observation.character_id not in {None, authoritative_character}:
                return "character_identity_mismatch"
        elif not bool(getattr(session, "memory_enabled", False)):
            return "system_memory_disabled"
        if observation.change_kind == "none":
            return "no_visual_change"
        if observation.importance < self._minimum_importance:
            return "importance_below_memory_threshold"
        if _observation_confidence(observation) < self._minimum_confidence:
            return "confidence_below_memory_threshold"
        if screen_prompt_injection_observed(observation.visible_text):
            return "screen_prompt_injection_detected"
        return None


def _observation_confidence(observation: DesktopObservation) -> float:
    values = [observation.current_scene.confidence]
    values.extend(item.confidence for item in observation.visible_changes)
    values.extend(item.confidence for item in observation.possible_events)
    return max(values, default=0.0)


def _safe_text(value: str, maximum: int = 420) -> str:
    compact = " ".join(str(value or "").split())
    compact = _URL.sub("[url]", compact)
    compact = _EMAIL.sub("[email]", compact)
    compact = _LONG_NUMBER.sub("[number]", compact)
    compact = _TOKENISH.sub("[token]", compact)
    return compact[:maximum]


def _memory_payload(observation: DesktopObservation) -> dict[str, Any]:
    confidence = _observation_confidence(observation)
    return {
        "kind": "desktop_activity_episode",
        "scene": _safe_text(observation.current_scene.value),
        "visible_changes": [
            {
                "event": _safe_text(item.event),
                "confidence": round(item.confidence, 4),
            }
            for item in observation.visible_changes[:4]
        ],
        "possible_events": [
            {
                "event": _safe_text(item.event),
                "confidence": round(item.confidence, 4),
            }
            for item in observation.possible_events[:3]
        ],
        "importance": round(observation.importance, 4),
        "confidence": round(confidence, 4),
        "activity": observation.activity.activity,
        "activity_hypothesis": observation.activity.hypothesis,
        "behavior_pattern": observation.behavior.current_pattern,
        "change_kind": observation.change_kind,
        "desktop_observation_id": observation.observation_id,
        "capture_generation": observation.capture_generation,
        "character_id": observation.character_id,
        "memory_hints": {
            "preferred_domains": ["episode", "open_loop"],
            "treat_as_external_observation": True,
        },
    }


_default_bridge: DesktopCompanionMemoryBridge | None = None


def default_desktop_companion_memory_bridge() -> DesktopCompanionMemoryBridge:
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = DesktopCompanionMemoryBridge()
    return _default_bridge


__all__ = [
    "DesktopCompanionMemoryBridge",
    "DesktopMemoryBridgeOutcome",
    "default_desktop_companion_memory_bridge",
]
