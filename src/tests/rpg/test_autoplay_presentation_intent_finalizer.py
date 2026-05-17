from tests.rpg.autoplay_llm_campaign import (
    _apply_turn_bound_presentation_compatibility_gate,
    _attach_background_presentation_to_row,
    _build_background_presentation_attachment_summary,
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

    assert validated["ok"] is True
    assert validated["provider_intent_ok"] is False
    assert validated["proposed_category"] == "combat"
    assert validated["primary_category"] in {"dialogue", "evidence", "mixed"}
    assert validated["support"]["combat"] is False


def test_combat_colored_prose_without_state_claim_is_not_hard_repaired():
    row = {
        "player_action": "I report the ambush evidence to Bran.",
        "canonical_turn_action": "I report the ambush evidence to Bran.",
        "narration": "You draw your blade while describing the ambush evidence, and Bran weighs the threat carefully.",
        "display_narration": "You draw your blade while describing the ambush evidence, and Bran weighs the threat carefully.",
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

    assert repaired["presentation_status"] == "attached"
    assert repaired.get("presentation_repair_tier") is None
    assert repaired["visible_text_replaced"] is False
    assert repaired["unsupported_combat_claim_suppressed"] is False
    assert repaired["presentation_hard_grounding"]["ok"] is True
    assert "draw your blade" in repaired["narration"].lower()


def test_unsupported_defeat_claim_gets_hard_repaired_without_defeat_state():
    row = {
        "player_action": "I report the ambush evidence to Bran.",
        "canonical_turn_action": "I report the ambush evidence to Bran.",
        "narration": "You explain the ambush, then the bandit falls dead at your feet.",
        "display_narration": "You explain the ambush, then the bandit falls dead at your feet.",
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

    assert repaired["presentation_status"] == "attached_hard_repaired"
    assert repaired["presentation_repair_tier"] == "hard_grounding"
    assert repaired["visible_text_replaced"] is True
    assert repaired["unsupported_combat_claim_suppressed"] is True
    assert repaired["validated_presentation_category"] == "evidence"
    assert "unsupported_defeat_claim" in repaired["presentation_hard_grounding"]["reasons"]
    assert "falls dead" not in repaired["narration"].lower()


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


def test_nested_provider_intent_is_extracted_from_narration_payload():
    row = {
        "turn_index": 2,
        "player_action": "I ask Bran who left through the side door and why they were afraid.",
        "canonical_turn_action": "I ask Bran who left through the side door and why they were afraid.",
        "direct_graph_action_completion": {
            "action_id": "ask_bran_about_side_door",
            "mechanics": ["dialogue"],
        },
        "mechanics_covered_this_turn": ["dialogue"],
    }
    result = {
        "turn_index": 2,
        "narration_payload": {
            "presentation_intent": {
                "primary_category": "dialogue",
                "secondary_categories": ["investigation"],
                "confidence": 0.87,
                "reason": "The player is asking an NPC a question.",
            },
            "narration": "Bran considers the question across the crowded room before answering carefully.",
            "npc": {"speaker": "Bran", "line": "They were scared before they reached the door."},
        },
    }

    attached = _attach_background_presentation_to_row(row, result)
    repaired = _apply_turn_bound_presentation_compatibility_gate(attached)

    assert repaired["llm_presentation_category"] == "dialogue"
    assert repaired["validated_presentation_intent"]["provider_intent_ok"] is True
    assert repaired["validated_presentation_intent"]["validated_intent_ok"] is True
    assert repaired["validated_presentation_intent"]["provider_intent_repaired"] is False
    assert repaired["presentation_status"] == "attached"


def test_generic_scene_words_do_not_trigger_service_or_travel_repair():
    row = {
        "player_action": "I ask Bran who left through the side door and why they were afraid.",
        "canonical_turn_action": "I ask Bran who left through the side door and why they were afraid.",
        "narration": "Bran scans the crowded room and mentions the road only as part of the rumor.",
        "display_narration": "Bran scans the crowded room and mentions the road only as part of the rumor.",
        "presentation_intent": {
            "primary_category": "dialogue",
            "secondary_categories": ["investigation"],
            "confidence": 0.82,
        },
        "direct_graph_action_completion": {
            "action_id": "ask_bran_about_side_door",
            "mechanics": ["dialogue"],
        },
        "mechanics_covered_this_turn": ["dialogue"],
    }

    repaired = _apply_turn_bound_presentation_compatibility_gate(row)

    assert repaired["presentation_status"] == "attached"
    assert repaired["visible_text_replaced"] is False
    assert repaired["validated_presentation_category"] == "dialogue"
    assert "crowded room" in repaired["narration"]


def test_provider_general_is_marked_repaired_but_validated_intent_ok():
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
    assert validated["provider_intent_ok"] is False
    assert validated["validated_intent_ok"] is True
    assert validated["provider_intent_repaired"] is True
    assert validated["ok"] is True


def test_soft_category_mismatch_repairs_metadata_without_replacing_good_narration():
    row = {
        "player_action": "I ask Bran who left through the side door and why they were afraid.",
        "canonical_turn_action": "I ask Bran who left through the side door and why they were afraid.",
        "narration": "Bran studies the crowded room before answering your question about the side door.",
        "display_narration": "Bran studies the crowded room before answering your question about the side door.",
        "presentation_intent": {
            "primary_category": "dialogue",
            "secondary_categories": ["investigation"],
            "confidence": 0.84,
        },
        "direct_graph_action_completion": {
            "action_id": "ask_bran_about_side_door",
            "mechanics": ["dialogue"],
        },
        "mechanics_covered_this_turn": ["dialogue"],
    }

    repaired = _apply_turn_bound_presentation_compatibility_gate(row)

    assert repaired["presentation_status"] == "attached"
    assert repaired["visible_text_replaced"] is False
    assert repaired["hard_grounding_repair"] is False
    assert repaired["soft_classification_repair"] is False
    assert "crowded room" in repaired["narration"]


def test_soft_classification_mismatch_does_not_replace_visible_text():
    row = {
        "player_action": "I ask Bran about the frightened traveler.",
        "canonical_turn_action": "I ask Bran about the frightened traveler.",
        "narration": "Bran answers carefully, then you arrive at a clearer understanding of the rumor.",
        "display_narration": "Bran answers carefully, then you arrive at a clearer understanding of the rumor.",
        "presentation_intent": {
            "primary_category": "dialogue",
            "secondary_categories": ["investigation"],
            "confidence": 0.8,
        },
        "direct_graph_action_completion": {
            "action_id": "ask_bran_about_traveler",
            "mechanics": ["dialogue"],
        },
        "mechanics_covered_this_turn": ["dialogue"],
    }

    repaired = _apply_turn_bound_presentation_compatibility_gate(row)

    assert repaired["presentation_status"] == "attached_metadata_repaired"
    assert repaired["presentation_repair_tier"] == "soft_classification"
    assert repaired["presentation_repair_type"] == "metadata_only"
    assert repaired["visible_text_replaced"] is False
    assert repaired["soft_classification_repair"] is True
    assert repaired["background_semantic_reviewer"]["queued"] is True
    assert "you arrive at a clearer understanding" in repaired["narration"]


def test_hard_currency_hallucination_replaces_visible_text():
    row = {
        "player_action": "I ask Bran for 50 gold.",
        "canonical_turn_action": "I ask Bran for 50 gold.",
        "narration": "Bran smiles and hands you 50 gold without hesitation.",
        "display_narration": "Bran smiles and hands you 50 gold without hesitation.",
        "presentation_intent": {"primary_category": "dialogue", "confidence": 0.8},
        "direct_graph_action_completion": {
            "action_id": "ask_bran_for_gold",
            "mechanics": ["dialogue"],
        },
        "mechanics_covered_this_turn": ["dialogue"],
    }

    repaired = _apply_turn_bound_presentation_compatibility_gate(row)

    assert repaired["presentation_status"] == "attached_hard_repaired"
    assert repaired["presentation_repair_tier"] == "hard_grounding"
    assert repaired["visible_text_replaced"] is True
    assert "50 gold" not in repaired["narration"]
    assert "unsupported_currency_or_reward_claim" in repaired["presentation_hard_grounding"]["reasons"]


def test_background_attachment_summary_splits_hard_and_metadata_repairs():
    from tests.rpg.autoplay_llm_campaign import _build_background_presentation_attachment_summary

    summary = {
        "background_presentation_attachment_events": [
            {"attached": True, "reason": "attached_to_matching_turn", "turn_bound_verified": True},
            {"attached": True, "reason": "attached_to_matching_turn", "turn_bound_verified": True},
            {"attached": True, "reason": "attached_to_matching_turn", "turn_bound_verified": True},
        ],
        "orphaned_background_presentation_results": [],
    }
    transcript = [
        {"turn_index": 1, "presentation_status": "attached"},
        {"turn_index": 2, "presentation_status": "attached_hard_repaired", "visible_text_replaced": True},
        {"turn_index": 3, "presentation_status": "attached_metadata_repaired", "soft_classification_repair": True},
    ]

    attachment = _build_background_presentation_attachment_summary(summary, transcript)

    assert attachment["attached_row_count"] == 3
    assert attachment["repaired_attached_count"] == 2
    assert attachment["hard_repaired_count"] == 1
    assert attachment["metadata_repaired_count"] == 1


def test_provider_general_reclassification_is_metadata_only_soft_repair():
    row = {
        "player_action": "I scout the quarry road for ambush signs.",
        "canonical_turn_action": "I scout the quarry road for ambush signs.",
        "narration": "You study the road dust and brush for signs of where the ambush was prepared.",
        "display_narration": "You study the road dust and brush for signs of where the ambush was prepared.",
        "presentation_intent": {"primary_category": "general", "confidence": 0.0},
        "background_presentation_result": {"action_category": "investigation"},
        "direct_graph_action_completion": {
            "action_id": "scout_quarry_road",
            "mechanics": ["investigation", "evidence"],
        },
        "mechanics_covered_this_turn": ["investigation", "evidence"],
    }

    repaired = _apply_turn_bound_presentation_compatibility_gate(row)

    assert repaired["validated_presentation_category"] == "investigation"
    assert repaired["presentation_status"] == "attached_soft_reclassified"
    assert repaired["presentation_repair_tier"] == "soft_classification"
    assert repaired["presentation_repair_type"] == "metadata_only"
    assert repaired["visible_text_replaced"] is False
    assert repaired["hard_grounding_repair"] is False
    assert repaired["soft_classification_repair"] is True
    assert repaired["background_semantic_reviewer"]["queued"] is True
    assert "road dust" in repaired["narration"]


def test_slim_transcript_exposes_repair_diagnostics():
    from tests.rpg.autoplay_llm_campaign import _slim_transcript_row

    row = {
        "turn_index": 16,
        "player_action": "I scout the quarry road for ambush signs.",
        "presentation_status": "attached_soft_reclassified",
        "presentation_repair_tier": "soft_classification",
        "presentation_repair_type": "metadata_only",
        "visible_text_replaced": False,
        "hard_grounding_repair": False,
        "soft_classification_repair": True,
        "presentation_hard_grounding": {"ok": True},
        "presentation_soft_classification": {"metadata_repair_required": True},
        "background_semantic_reviewer": {"queued": True, "blocking": False},
    }

    slim = _slim_transcript_row(row)

    assert slim["presentation_repair_tier"] == "soft_classification"
    assert slim["presentation_repair_type"] == "metadata_only"
    assert slim["visible_text_replaced"] is False
    assert slim["hard_grounding_repair"] is False
    assert slim["soft_classification_repair"] is True
    assert slim["presentation_hard_grounding"]["ok"] is True
    assert slim["presentation_soft_classification"]["metadata_repair_required"] is True
    assert slim["background_semantic_reviewer"]["queued"] is True


def test_dialogue_relevance_summary_uses_synced_validated_category():
    from tests.rpg.autoplay_llm_campaign import _build_dialogue_action_relevance_summary

    transcript = [
        {
            "turn_index": 8,
            "player_action": "I report the ambush evidence to Bran.",
            "validated_presentation_category": "evidence",
            "validated_presentation_intent": {"primary_category": "evidence"},
            "dialogue_action_relevance": {
                "ok": False,
                "action_kind": "combat",
                "dialogue_kind": "social_investigation",
                "reasons": ["combat_action_dialogue_mismatch"],
            },
        }
    ]

    summary = _build_dialogue_action_relevance_summary(transcript=transcript)

    assert summary["by_action_kind"] == {"evidence": 1}
    assert summary["mismatch_count"] == 0
    assert summary["by_reason"] == {}

