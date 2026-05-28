from __future__ import annotations

import json

from app.rpg.ai.survival_narration_grounding import (
    build_survival_narration_evidence,
    sanitize_survival_narration_payload,
    sanitize_survival_narration_text,
    survival_narration_prompt_block,
    validate_survival_narration_text,
)


def _context_with_survival_result(action, *, effects=None, inventory_delta=None, ok=True, blocked_reason=""):
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
        "resolved_result": {
            "survival_result": survival_result,
        },
        "turn_contract": {
            "resolved_result": {
                "survival_result": survival_result,
            }
        },
    }


def test_bundle_bs_builds_prompt_evidence_from_authoritative_survival_result() -> None:
    context = _context_with_survival_result(
        "drink_water",
        effects={"thirst_delta": -30},
        inventory_delta={"water": -1},
    )

    evidence = build_survival_narration_evidence(context)
    block = survival_narration_prompt_block(context)

    assert evidence["format_version"] == "survival_narration_grounding_v1"
    assert evidence["survival"] == {"hunger": 70, "thirst": 80, "fatigue": 65}
    assert "water" in evidence["backed_categories"]
    assert evidence["effects"] == {"thirst_delta": -60} or evidence["effects"] == {"thirst_delta": -30}
    assert evidence["inventory_delta"] in ({"water": -2}, {"water": -1})
    assert "Survival grounding contract" in block
    assert "Current survival" in block
    assert "Backed survival categories" in block
    json.dumps(evidence)


def test_bundle_bs_allows_water_claim_when_authoritative_water_evidence_exists() -> None:
    context = _context_with_survival_result(
        "drink_water",
        effects={"thirst_delta": -30},
        inventory_delta={"water": -1},
    )

    validation = validate_survival_narration_text(
        "You drink the water, and your thirst eases.",
        context,
    )

    assert validation["ok"] is True
    assert validation["violations"] == []


def test_bundle_bs_blocks_invented_water_meal_rest_supplies_and_healing_claims() -> None:
    context = {
        "resolved_result": {
            "message": "The action resolves.",
            "survival": {"hunger": 70, "thirst": 80, "fatigue": 65},
        }
    }

    text = (
        "You find clean water and refill your waterskin. "
        "A hot meal leaves you fed. "
        "The inn bed refreshes you. "
        "Your wounds heal as supplies are added to your pack."
    )
    validation = validate_survival_narration_text(text, context)

    assert validation["ok"] is False
    categories = {row["category"] for row in validation["violations"]}
    assert "water" in categories
    assert "food" in categories
    assert "rest" in categories
    assert "supplies" in categories
    assert "healing" in categories


def test_bundle_bs_sanitizes_invented_survival_sentences_but_keeps_grounded_scene_text() -> None:
    context = {
        "resolved_result": {
            "survival": {"hunger": 70, "thirst": 80, "fatigue": 65},
        },
        "authoritative_fallback": "The action resolves according to the current survival state.",
    }

    sanitized = sanitize_survival_narration_text(
        "The tavern goes quiet. You drink from a hidden spring and feel refreshed.",
        context,
    )

    assert sanitized == "The tavern goes quiet."


def test_bundle_bs_payload_sanitizer_validates_narration_action_and_npc_line() -> None:
    context = _context_with_survival_result(
        "tavern_meal",
        effects={"hunger_delta": -35},
        inventory_delta={},
    )
    payload = {
        "format_version": "rpg_narration_v2",
        "narration": "The meal eases your hunger. Your waterskin is magically full.",
        "action": "The tavern meal is served.",
        "npc": {"speaker": "Bran", "line": "That meal is settled."},
        "reward": "",
        "followup_hooks": [],
    }

    sanitized = sanitize_survival_narration_payload(payload, context)

    assert "meal eases your hunger" in sanitized["narration"].lower()
    assert "waterskin" not in sanitized["narration"].lower()
    assert sanitized["survival_narration_grounding"]["ok"] is True
    json.dumps(sanitized)


def test_bundle_bs_blocked_survival_action_does_not_authorize_success_narration() -> None:
    context = _context_with_survival_result(
        "drink_water",
        ok=False,
        blocked_reason="no_water_available",
    )

    validation = validate_survival_narration_text(
        "You drink water and your thirst is quenched.",
        context,
    )
    sanitized = sanitize_survival_narration_text(
        "You drink water and your thirst is quenched.",
        context,
        fallback="No water is available.",
    )

    assert validation["ok"] is False
    assert sanitized == "No water is available."
