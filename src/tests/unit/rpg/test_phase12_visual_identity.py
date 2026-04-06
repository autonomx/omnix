"""Phase 12 — Visual identity unit tests.

Tests for visual_state.py module covering:
- ensure_visual_state normalization
- build_default_character_visual_identity determinism
- upsert character portraits
- append scene illustrations with bounds
- append image requests with bounds
"""
from app.rpg.presentation.visual_state import (
    append_image_request,
    append_scene_illustration,
    build_default_character_visual_identity,
    ensure_visual_state,
    stable_visual_seed_from_text,
    upsert_character_visual_identity,
    _stable_seed_from_text,
    _normalize_visual_identity_entry,
    _normalize_scene_illustration,
    _normalize_image_request,
    _safe_str,
    _safe_int,
)


def test_ensure_visual_state_empty():
    result = ensure_visual_state({})
    visual_state = result["presentation_state"]["visual_state"]
    assert visual_state["character_visual_identities"] == {}
    assert visual_state["scene_illustrations"] == []
    assert visual_state["image_requests"] == []
    assert "defaults" in visual_state
    assert visual_state["defaults"]["portrait_style"] == "rpg-portrait"
    assert visual_state["defaults"]["scene_style"] == "rpg-scene"


def test_ensure_visual_state_idempotent():
    one = ensure_visual_state({})
    two = ensure_visual_state(dict(one))
    assert one["presentation_state"]["visual_state"] == two["presentation_state"]["visual_state"]


def test_build_default_character_visual_identity_stable():
    one = build_default_character_visual_identity(
        actor_id="npc:guard",
        name="Captain Elira",
        role="guard_captain",
        description="Veteran commander",
        personality_summary="Dry and practical",
        style="rpg-portrait",
        model="default",
    )
    two = build_default_character_visual_identity(
        actor_id="npc:guard",
        name="Captain Elira",
        role="guard_captain",
        description="Veteran commander",
        personality_summary="Dry and practical",
        style="rpg-portrait",
        model="default",
    )
    assert one == two
    assert one["seed"] is not None
    assert one["status"] == "idle"
    assert one["version"] == 1
    assert one["portrait_url"] == ""
    assert one["portrait_asset_id"] == ""


def test_build_default_character_visual_identity_contains_parts():
    identity = build_default_character_visual_identity(
        actor_id="npc:smith",
        name="Ironforge",
        role="blacksmith",
        description="Master craftsman",
        personality_summary="Gruff but kind",
        style="rpg-portrait",
        model="default",
    )
    assert "Ironforge" in identity["base_prompt"]
    assert "blacksmith" in identity["base_prompt"]
    assert identity["style"] == "rpg-portrait"


def test_stable_seed_deterministic():
    one = _stable_seed_from_text("hello world")
    two = _stable_seed_from_text("hello world")
    assert one == two
    assert isinstance(one, int) and one > 0


def test_stable_seed_different_for_different_text():
    one = _stable_seed_from_text("alpha")
    two = _stable_seed_from_text("beta")
    assert one != two


def test_stable_visual_seed_from_text_is_deterministic():
    one = stable_visual_seed_from_text("scene:test|event:test|Market Clash|rpg-scene|default")
    two = stable_visual_seed_from_text("scene:test|event:test|Market Clash|rpg-scene|default")
    assert one == two
    assert isinstance(one, int)
    assert one > 0


def test_upsert_character_visual_identity():
    simulation_state = {}
    simulation_state = upsert_character_visual_identity(
        simulation_state,
        actor_id="npc:test",
        identity={
            "seed": 123,
            "style": "rpg-portrait",
            "base_prompt": "test prompt",
            "model": "default",
            "version": 1,
            "status": "pending",
        },
    )
    identities = simulation_state["presentation_state"]["visual_state"]["character_visual_identities"]
    assert "npc:test" in identities
    assert identities["npc:test"]["seed"] == 123


def test_upsert_visual_identity_overwrites():
    simulation_state = {}
    simulation_state = upsert_character_visual_identity(
        simulation_state,
        actor_id="npc:test",
        identity={"seed": 100, "style": "style-a", "base_prompt": "first", "model": "default", "version": 1, "status": "idle"},
    )
    simulation_state = upsert_character_visual_identity(
        simulation_state,
        actor_id="npc:test",
        identity={"seed": 200, "style": "style-b", "base_prompt": "second", "model": "other", "version": 2, "status": "complete"},
    )
    identity = simulation_state["presentation_state"]["visual_state"]["character_visual_identities"]["npc:test"]
    assert identity["seed"] == 200
    assert identity["style"] == "style-b"
    assert identity["version"] == 2


def test_append_scene_illustration_bounded_and_sorted():
    simulation_state = {}
    for i in range(30):
        simulation_state = append_scene_illustration(
            simulation_state,
            {
                "scene_id": f"scene:{i}",
                "event_id": f"event:{i}",
                "title": f"Scene {i}",
            },
        )
    illustrations = simulation_state["presentation_state"]["visual_state"]["scene_illustrations"]
    assert len(illustrations) == 24


def test_append_image_request_bounded():
    simulation_state = {}
    for i in range(30):
        simulation_state = append_image_request(
            simulation_state,
            {
                "request_id": f"req:{i}",
                "kind": "character_portrait",
                "target_id": f"npc:{i}",
            },
        )
    requests = simulation_state["presentation_state"]["visual_state"]["image_requests"]
    assert len(requests) == 24


def test_normalize_visual_identity_entry_defaults():
    result = _normalize_visual_identity_entry({})
    assert result["status"] == "idle"
    assert result["version"] == 1
    assert result["portrait_url"] == ""
    assert result["style"] == ""


def test_normalize_scene_illustration_defaults():
    result = _normalize_scene_illustration({})
    assert result["status"] == "idle"
    assert result["scene_id"] == ""
    assert result["title"] == ""


def test_normalize_image_request_defaults():
    result = _normalize_image_request({})
    assert result["kind"] == "character_portrait"
    assert result["status"] == "pending"
    assert result["request_id"] == ""


def test_normalize_image_request_rejects_invalid_kind():
    result = _normalize_image_request({"kind": "something_else"})
    assert result["kind"] == "character_portrait"


def test_normalize_image_request_rejects_invalid_status():
    result = _normalize_image_request({"status": "invalid"})
    assert result["status"] == "pending"


def test_safe_str_handles_none():
    assert _safe_str(None) == ""


def test_safe_int_handles_invalid():
    assert _safe_int("not_a_number") is None
    assert _safe_int(42) == 42
    assert _safe_int(True) == 1