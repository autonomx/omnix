"""Unit tests for Phase 13.4 — New Adventure Wizard UI."""
from app.rpg.setup.wizard_state import (
    build_wizard_preview_payload,
    build_wizard_setup_payload,
    normalize_wizard_state,
)


def test_normalize_wizard_state_basic():
    result = normalize_wizard_state({"title": "Adventure"})
    assert result["title"] == "Adventure"


def test_build_wizard_preview_payload():
    result = build_wizard_preview_payload({"title": "Adventure", "character_seeds": []})
    assert result["title"] == "Adventure"


def test_build_wizard_setup_payload():
    result = build_wizard_setup_payload({"title": "Adventure"})
    assert "simulation_state" in result


def test_normalize_wizard_state_defaults():
    result = normalize_wizard_state({})
    assert result["step"] == "mode"
    assert result["mode"] == "blank"
    assert result["title"] == ""
    assert result["summary"] == ""
    assert result["opening"] == ""
    assert result["selected_pack"] == {}
    assert result["selected_template"] == {}
    assert result["world_seed"] == {}
    assert result["character_seeds"] == []
    assert result["visual_defaults"] == {}


def test_normalize_wizard_strips_whitespace():
    result = normalize_wizard_state({"title": "  Adventure  "})
    assert result["title"] == "Adventure"


def test_character_seeds_capped_at_max():
    seeds = [{"canonical_seed": {}} for _ in range(20)]
    result = normalize_wizard_state({"character_seeds": seeds})
    assert len(result["character_seeds"]) == 16


def test_build_wizard_setup_payload_has_wizard_state():
    result = build_wizard_setup_payload({"title": "Test"})
    assert "wizard_state" in result