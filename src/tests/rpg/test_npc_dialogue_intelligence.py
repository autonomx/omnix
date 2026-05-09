from app.rpg.npc_dialogue.intelligence import npc_line_is_invalid, normalize_npc_intelligence_payload


def test_npc_line_validator_rejects_repeated_lines():
    recent = ["The cloaked traveler left by the side door."]
    assert npc_line_is_invalid("The cloaked traveler left by the side door.", recent)


def test_npc_line_validator_rejects_meta_or_generic_objective():
    assert npc_line_is_invalid("As an AI, I cannot help.", [])
    assert npc_line_is_invalid("Tell me about your current objective.", [])


def test_npc_intelligence_payload_normalizes_line():
    payload = normalize_npc_intelligence_payload(
        {
            "intent": "redirect_to_clue",
            "known_fact_used": "side door",
            "line": "Check the side door before the rain takes the tracks.",
            "next_hook": "inspect_tavern_exit",
        }
    )
    assert payload["line"].startswith("Check the side door")