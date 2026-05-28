from __future__ import annotations

import json

from app.rpg.ai.world_scene_survival_grounding_bridge import (
    append_survival_grounding_to_prompt,
    force_patch_world_scene_narrator,
    sanitize_world_scene_survival_payload,
)


def _scene():
    return {
        "title": "The Rusty Flagon",
        "summary": "A smoky tavern room hums with quiet tension.",
        "actors": [{"id": "npc:bran", "name": "Bran"}],
        "location_name": "The Rusty Flagon",
    }


def _context(action="drink_water", *, ok=True, blocked_reason="", effects=None, inventory_delta=None):
    survival_result = {
        "ok": ok,
        "action_category": "survival",
        "action": action,
        "effects": effects or {},
        "inventory_delta": inventory_delta or {},
        "survival": {"hunger": 70, "thirst": 80, "fatigue": 65},
    }
    if blocked_reason:
        survival_result["blocked_reason"] = blocked_reason
    return {
        "player_input": "drink water",
        "action_type": "survival",
        "resolved_result": {
            "message": "The survival action resolves.",
            "survival_result": survival_result,
        },
        "turn_contract": {
            "narration_brief": {"summary": "A survival action resolves."},
            "resolved_result": {"survival_result": survival_result},
        },
        "simulation_state": {
            "survival": {"hunger": 70, "thirst": 80, "fatigue": 65, "events": []},
        },
    }


def test_bundle_bs1_prompt_bridge_appends_survival_grounding_when_evidence_exists() -> None:
    prompt = append_survival_grounding_to_prompt("BASE PROMPT", _context(effects={"thirst_delta": -30}, inventory_delta={"water": -1}))

    assert prompt.startswith("BASE PROMPT")
    assert "Survival grounding contract" in prompt
    assert "Current survival" in prompt
    assert "Successful authoritative survival actions" in prompt or "Authoritative survival actions" in prompt
    assert "drink_water" in prompt


def test_bundle_bs1_prompt_bridge_is_noop_without_survival_evidence() -> None:
    assert append_survival_grounding_to_prompt("BASE PROMPT", {"resolved_result": {}}) == "BASE PROMPT"


def test_bundle_bs1_payload_bridge_removes_invented_survival_claims_after_legacy_sanitize() -> None:
    context = _context(effects={"thirst_delta": -30}, inventory_delta={"water": -1})
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "You drink the water, and your thirst eases. A meal appears and leaves you fed.",
        "action": "You drink the water.",
        "npc": {"speaker": "Bran", "line": "That water is yours."},
        "reward": "",
        "followup_hooks": [],
        "grounding_validation": {"ok": True},
    }

    sanitized = sanitize_world_scene_survival_payload(payload, context)

    assert "thirst eases" in sanitized["narration"]
    assert "meal appears" not in sanitized["narration"]
    assert sanitized["grounding_validation"] == {"ok": True}
    assert sanitized["survival_narration_grounding"]["ok"] is True
    json.dumps(sanitized)


def test_bundle_bs1_payload_bridge_blocks_success_claim_for_blocked_survival_action() -> None:
    context = _context(ok=False, blocked_reason="no_water_available")
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "You drink water and your thirst is quenched.",
        "action": "You drink water.",
        "npc": {"speaker": "Bran", "line": "The water is yours."},
        "reward": "",
        "followup_hooks": [],
    }

    sanitized = sanitize_world_scene_survival_payload(payload, context)

    blob = " ".join([sanitized.get("narration", ""), sanitized.get("action", ""), sanitized.get("npc", {}).get("line", "")]).lower()
    assert "quenched" not in blob
    assert "the water is yours" not in blob
    assert sanitized["survival_narration_grounding"]["ok"] is True


def test_bundle_bs1_force_patch_world_scene_narrator_prompt_and_sanitize_paths() -> None:
    narrator = force_patch_world_scene_narrator()
    assert getattr(narrator, "_BS1_SURVIVAL_GROUNDING_PATCHED") is True

    context = _context(effects={"thirst_delta": -30}, inventory_delta={"water": -1})
    prompt = narrator.build_scene_prompt(_scene(), context)
    assert "Survival grounding contract" in prompt
    assert "drink_water" in prompt

    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "You drink the water, and your thirst eases. A warm bed refreshes you.",
        "action": "You drink water.",
        "npc": {"speaker": "Bran", "line": "The water is yours."},
        "reward": "",
        "followup_hooks": [],
    }
    sanitized = narrator._sanitize_narration_payload(payload, _scene(), context)
    assert "thirst eases" in sanitized["narration"]
    assert "warm bed" not in sanitized["narration"]
    assert sanitized["survival_narration_grounding"]["ok"] is True
