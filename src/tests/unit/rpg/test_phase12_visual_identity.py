"""Phase 12 — Visual identity unit tests.

Tests for visual_state.py module covering:
- ensure_visual_state normalization
- build_default_character_visual_identity determinism
- upsert character portraits
- append scene illustrations with bounds
- append image requests with bounds
- visual assets, appearance profiles, appearance events (Phase 12.3/12.4)
- prompt validation, moderation, fallback (Phase 12.5)
"""
from app.rpg.presentation.visual_state import (
    append_appearance_event,
    append_image_request,
    append_scene_illustration,
    append_visual_asset,
    apply_visual_fallback,
    build_default_appearance_profile,
    build_default_character_visual_identity,
    build_visual_asset_record,
    ensure_visual_state,
    normalize_visual_status,
    stable_visual_seed_from_text,
    upsert_appearance_profile,
    upsert_character_visual_identity,
    validate_visual_prompt,
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
    assert visual_state["visual_assets"] == []
    assert visual_state["appearance_profiles"] == {}
    assert visual_state["appearance_events"] == {}
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


# ---- Phase 12.3 — Visual assets ----


def test_build_default_appearance_profile():
    profile = build_default_appearance_profile(
        actor_id="npc:guard",
        name="Captain Elira",
        role="guard_captain",
        description="Veteran commander",
    )
    assert profile["version"] == 1
    assert profile["last_reason"] == "initial"
    assert "Captain Elira" in profile["base_description"]


def test_append_visual_asset_bounded():
    simulation_state = {}
    for i in range(80):
        simulation_state = append_visual_asset(
            simulation_state,
            {
                "asset_id": f"asset:{i}",
                "kind": "character_portrait",
                "target_id": f"npc:{i}",
                "version": 1,
            },
        )
    assets = simulation_state["presentation_state"]["visual_state"]["visual_assets"]
    assert len(assets) == 64


def test_upsert_appearance_profile_and_events():
    simulation_state = {}
    simulation_state = upsert_appearance_profile(
        simulation_state,
        actor_id="npc:test",
        profile={"current_summary": "scarred veteran", "version": 2},
    )
    simulation_state = append_appearance_event(
        simulation_state,
        actor_id="npc:test",
        event={"event_id": "e1", "reason": "injury", "summary": "Scar gained", "tick": 3},
    )
    visual_state = simulation_state["presentation_state"]["visual_state"]
    assert visual_state["appearance_profiles"]["npc:test"]["version"] == 2
    assert len(visual_state["appearance_events"]["npc:test"]) == 1


# ---- Phase 12.5 — Validation, moderation, fallback ----


def test_validate_visual_prompt():
    assert validate_visual_prompt("portrait of a stern guard")["ok"] is True
    assert validate_visual_prompt("")["ok"] is False
    assert validate_visual_prompt("x" * 2001)["ok"] is False


def test_apply_visual_fallback():
    payload = {"portrait_url": "", "status": "failed"}
    out = apply_visual_fallback(payload, "/fallback.png")
    assert out["portrait_url"] == "/fallback.png"


def test_normalize_visual_status():
    assert normalize_visual_status("complete") == "complete"
    assert normalize_visual_status("weird") == "pending"
    assert normalize_visual_status(None) == "pending"


def test_build_visual_asset_record():
    asset = build_visual_asset_record(
        kind="character_portrait",
        target_id="npc:guard",
        version=2,
        seed=123,
        style="rpg-portrait",
        model="default",
        prompt="guard portrait",
        url="/img.png",
        local_path="/tmp/img.png",
        status="complete",
        created_from_request_id="req:1",
    )
    assert asset["asset_id"].startswith("character_portrait:npc:guard:2:")
    assert asset["cache_key"].startswith("character_portrait|npc:guard|2|")
    assert asset["moderation"]["status"] == "unchecked"


def test_apply_visual_fallback_preserves_fallback_when_result_url_empty():
    identity = {
        "portrait_url": "",
        "portrait_asset_id": "",
        "status": "failed",
    }
    out = apply_visual_fallback(identity, "/fallback.png")
    assert out["portrait_url"] == "/fallback.png"
