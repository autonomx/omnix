from __future__ import annotations

from app.rpg.session.fast_turn_model_routing import (
    MODEL_ROUTING_VERSION,
    classify_fast_turn_mode,
    route_for_player_turn,
    select_fast_turn_model_route,
)


def test_classify_fast_turn_mode_uses_deterministic_keywords() -> None:
    assert classify_fast_turn_mode("I buy two rations") == "service_fast"
    assert classify_fast_turn_mode("I look for tracks") == "investigation_fast"
    assert classify_fast_turn_mode("I travel to the quarry") == "travel_fast"
    assert classify_fast_turn_mode("I attack the shambler") == "combat_event_fast"
    assert classify_fast_turn_mode("Ask Bran about rumors") == "dialogue_fast"


def test_select_fast_turn_model_route_uses_routine_fast_tier() -> None:
    route = select_fast_turn_model_route(mode="combat_event_fast")

    assert route.format_version == MODEL_ROUTING_VERSION
    assert route.tier == "fast"
    assert route.max_output_tokens == 80
    assert route.stream is True
    assert route.blocking is True


def test_select_fast_turn_model_route_uses_large_tier_for_major_beats() -> None:
    route = select_fast_turn_model_route(mode="story_beat_high_quality", max_output_tokens=900)

    assert route.tier == "large"
    assert route.max_output_tokens == 800
    assert route.reason == "major_story_beat"


def test_background_routes_are_non_blocking() -> None:
    route = select_fast_turn_model_route(mode="memory_background")

    assert route.tier == "small"
    assert route.blocking is False
    assert route.stream is False


def test_route_for_player_turn_preserves_provider_and_model() -> None:
    route = route_for_player_turn("listen at the door", provider_id="lmstudio", model_id="small-local")

    assert route["mode"] == "investigation_fast"
    assert route["provider_id"] == "lmstudio"
    assert route["model_id"] == "small-local"
