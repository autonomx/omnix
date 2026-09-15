from __future__ import annotations

from datetime import datetime, timezone

from app.companion_activity.cognition import DeliveryIntent
from app.companion_activity.embodiment import CompanionEmbodimentMapper, RendererCapabilities

NOW = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)


def intent(kind: str, salience: float = 0.5) -> DeliveryIntent:
    return DeliveryIntent(
        intent_id=f"intent:{kind.lower()}",
        session_id="chat:1",
        kind=kind,
        reason="embodiment test",
        confidence=0.9,
        salience=salience,
        created_at=NOW,
    )


def test_semantic_state_is_independent_from_renderer_names() -> None:
    mapper = CompanionEmbodimentMapper()
    cue = mapper.cue_for_intent(intent("CELEBRATE", 0.92))

    assert cue.semantic_state == "celebrating"
    assert cue.intensity == 0.92


def test_capability_mapping_uses_supported_aliases_and_degrades_gracefully() -> None:
    mapper = CompanionEmbodimentMapper()
    cue = mapper.cue_for_intent(intent("CELEBRATE"))

    rich = mapper.map(
        cue,
        RendererCapabilities(
            expressions=("neutral", "happy"),
            motions=("idle", "cheer"),
            supports_intensity=True,
        ),
    )
    assert rich.expression == "happy"
    assert rich.motion == "cheer"
    assert rich.expose_intensity is True

    limited = mapper.map(
        cue,
        RendererCapabilities(expressions=("neutral",), motions=("idle",)),
    )
    assert limited.semantic_state == "celebrating"
    assert limited.expression is None
    assert limited.motion is None
    assert limited.expose_intensity is False


def test_warning_maps_to_alert_without_hardcoding_a_pack_specific_expression() -> None:
    mapper = CompanionEmbodimentMapper()
    cue = mapper.cue_for_intent(intent("WARN", 0.8))
    plan = mapper.map(
        cue,
        RendererCapabilities(expressions=("concerned",), motions=("warn",)),
    )

    assert cue.semantic_state == "alert"
    assert cue.intensity == 1.0
    assert plan.expression == "concerned"
    assert plan.motion == "warn"


def test_ignore_produces_neutral_zero_intensity_semantics() -> None:
    cue = CompanionEmbodimentMapper().cue_for_intent(intent("IGNORE", 1.0))
    assert cue.semantic_state == "neutral"
    assert cue.intensity == 0.0
