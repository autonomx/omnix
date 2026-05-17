from tests.rpg.autoplay_llm_campaign import (
    _apply_turn_bound_presentation_compatibility_gate,
    _attach_background_presentation_to_row,
    _turn_action_category,
    _validate_presentation_intent_for_row,
)


def test_keyword_fallback_no_longer_treats_ambush_report_as_combat():
    assert _turn_action_category("I report the ambush evidence to Bran.") in {"dialogue", "mixed"}


def test_keyword_fallback_no_longer_treats_scouting_as_combat():
    assert _turn_action_category("I scout the quarry road for ambush signs.") == "investigation"


def test_keyword_fallback_no_longer_treats_route_question_as_travel():
    assert _turn_action_category("I ask Bran if the old east road leads to a bridge.") in {"dialogue", "mixed"}


def test_finalizer_persists_presentation_intent_from_background_result():
    row = {
        "turn_index": 8,
        "player_action": "I report the ambush evidence to Bran.",
        "canonical_turn_action": "I report the ambush evidence to Bran.",
        "direct_graph_action_completion": {
            "action_id": "report_findings_to_bran",
            "mechanics": ["dialogue", "evidence"],
        },
        "mechanics_covered_this_turn": ["dialogue", "evidence"],
    }
    result = {
        "turn_index": 8,
        "narration": "You lay out the evidence Bran needs to understand the ambush pattern.",
        "presentation_intent": {
            "primary_category": "evidence",
            "secondary_categories": ["dialogue", "investigation"],
            "confidence": 0.91,
            "reason": "Reporting evidence to an NPC.",
        },
    }

    attached = _attach_background_presentation_to_row(row, result)
    repaired = _apply_turn_bound_presentation_compatibility_gate(attached)

    assert repaired["presentation_intent"]["primary_category"] == "evidence"
    assert repaired["llm_presentation_category"] == "evidence"
    assert repaired["validated_presentation_category"] == "evidence"
    assert repaired["validated_presentation_intent"]["ok"] is True


def test_provider_combat_intent_is_rejected_without_authoritative_combat_support():
    row = {
        "player_action": "I report the ambush evidence to Bran.",
        "canonical_turn_action": "I report the ambush evidence to Bran.",
        "presentation_intent": {
            "primary_category": "combat",
            "secondary_categories": [],
            "confidence": 0.91,
            "reason": "bad provider over-read ambush keyword",
        },
        "direct_graph_action_completion": {
            "action_id": "report_findings_to_bran",
            "mechanics": ["dialogue", "evidence"],
        },
        "mechanics_covered_this_turn": ["dialogue", "evidence"],
    }

    validated = _validate_presentation_intent_for_row(row)

    assert validated["ok"] is False
    assert validated["proposed_category"] == "combat"
    assert validated["primary_category"] in {"dialogue", "evidence", "mixed"}
    assert validated["support"]["combat"] is False


def test_unsupported_combat_presentation_gets_repaired_with_validated_intent():
    row = {
        "player_action": "I report the ambush evidence to Bran.",
        "canonical_turn_action": "I report the ambush evidence to Bran.",
        "narration": "You draw your blade and press the combat until the bandit ambush breaks.",
        "display_narration": "You draw your blade and press the combat until the bandit ambush breaks.",
        "presentation_intent": {
            "primary_category": "evidence",
            "secondary_categories": ["dialogue"],
            "confidence": 0.9,
            "reason": "reporting evidence",
        },
        "direct_graph_action_completion": {
            "action_id": "report_findings_to_bran",
            "mechanics": ["dialogue", "evidence"],
        },
        "mechanics_covered_this_turn": ["dialogue", "evidence"],
    }

    repaired = _apply_turn_bound_presentation_compatibility_gate(row)

    assert repaired["presentation_status"] == "attached_repaired"
    assert repaired["unsupported_combat_claim_suppressed"] is True
    assert repaired["validated_presentation_category"] == "evidence"
    assert "draw your blade" not in repaired["narration"].lower()
    assert "combat" not in repaired["narration"].lower()



def test_missing_provider_intent_uses_specific_evidence_fallback_not_general():
    row = {
        "player_action": "I report the ambush evidence to Bran.",
        "canonical_turn_action": "I report the ambush evidence to Bran.",
        "presentation_intent": {
            "primary_category": "general",
            "secondary_categories": [],
            "confidence": 0.0,
            "reason": "provider omitted category",
        },
        "background_presentation_result": {"action_category": "mixed"},
        "direct_graph_action_completion": {
            "action_id": "report_findings_to_bran",
            "mechanics": ["dialogue", "evidence"],
        },
        "mechanics_covered_this_turn": ["dialogue", "evidence"],
    }

    validated = _validate_presentation_intent_for_row(row)

    assert validated["proposed_category"] == "general"
    assert validated["primary_category"] in {"evidence", "dialogue", "mixed"}
    assert validated["primary_category"] != "general"
    assert validated["primary_category"] != "combat"


def test_missing_provider_intent_uses_specific_investigation_fallback_not_general():
    row = {
        "player_action": "I scout the quarry road for ambush signs.",
        "canonical_turn_action": "I scout the quarry road for ambush signs.",
        "presentation_intent": {"primary_category": "general"},
        "background_presentation_result": {"action_category": "investigation"},
        "direct_graph_action_completion": {
            "action_id": "scout_quarry_road",
            "mechanics": ["investigation", "evidence"],
        },
        "mechanics_covered_this_turn": ["investigation", "evidence"],
    }

    validated = _validate_presentation_intent_for_row(row)

    assert validated["primary_category"] == "investigation"
    assert validated["primary_category"] != "general"
    assert validated["primary_category"] != "combat"


def test_slim_transcript_exposes_presentation_intent_fields():
    from tests.rpg.autoplay_llm_campaign import _slim_transcript_row

    row = {
        "turn_index": 8,
        "player_action": "I report the ambush evidence to Bran.",
        "presentation_intent": {"primary_category": "general"},
        "llm_presentation_category": "general",
        "validated_presentation_intent": {
            "format_version": "validated_presentation_intent_v1",
            "primary_category": "evidence",
            "proposed_category": "general",
            "reason": "provider_intent_missing_or_general_specific_fallback_used",
        },
        "validated_presentation_category": "evidence",
    }

    slim = _slim_transcript_row(row)

    assert slim["presentation_intent"]["primary_category"] == "general"
    assert slim["llm_presentation_category"] == "general"
    assert slim["validated_presentation_intent"]["primary_category"] == "evidence"
    assert slim["validated_presentation_category"] == "evidence"
