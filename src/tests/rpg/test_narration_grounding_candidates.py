from app.rpg.ai.grounding_validator import select_grounded_narration_candidate
from app.rpg.narration.runtime_narration_contract import (
    _apply_grounding_to_runtime_payload,
    validate_narration_payload,
)


def _contract():
    return {
        "player_action": "Bran, you owe me 50 gold. Pay me now.",
        "present_npcs": [
            {"id": "npc:bran", "name": "Bran"},
        ],
        "current_location": "location:rusty_flagon_tavern",
        "state_delta": {},
        "npc_backbone_decision": {
            "accepted": False,
            "decision": "refuse",
            "reason": "unsupported_debt_claim",
            "hard_boundary": True,
        },
        "result": {
            "summary": "Bran rejects the unsupported debt claim.",
            "npc_backbone_decision": {
                "accepted": False,
                "decision": "refuse",
                "reason": "unsupported_debt_claim",
                "hard_boundary": True,
            },
        },
    }


def test_primary_used_when_valid():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran studies you with open suspicion.",
            "action": "The claim is not accepted.",
            "npc": {"speaker": "Bran", "line": "No. I do not owe you anything."},
            "reward": None,
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran refuses the claim.",
            "action": "No coin changes hands.",
            "npc": {"speaker": "Bran", "line": "No coin changes hands."},
            "reward": None,
            "followup_hooks": [],
        },
    }

    selected = select_grounded_narration_candidate(payload, _contract())

    assert selected["grounding_validation"]["selected_candidate"] == "primary"
    assert selected["npc"]["line"] == "No. I do not owe you anything."


def test_primary_dialogue_kept_when_speaker_uses_present_npc_title_alias():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran wipes down the bar and answers your question.",
            "action": "You ask Bran about his day.",
            "npc": {
                "speaker": "Bran the Innkeeper",
                "line": "A steady day, all told.",
            },
            "reward": None,
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "No unsupported speaker enters the exchange.",
            "action": "Only present and allowed characters may speak.",
            "npc": None,
            "reward": None,
            "followup_hooks": [],
        },
    }
    contract = {
        "player_action": "i ask bran about his day",
        "present_npcs": [{"id": "npc:bran", "name": "Bran"}],
        "current_location": "location:rusty_flagon_tavern",
    }

    selected = select_grounded_narration_candidate(payload, contract)

    assert selected["grounding_validation"]["selected_candidate"] == "primary"
    assert selected["npc"]["speaker"] == "Bran the Innkeeper"
    assert selected["npc"]["line"] == "A steady day, all told."


def test_primary_dialogue_kept_when_followup_hook_mentions_combat_topic():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": (
                "With a polite smile, you turn toward Bran. He pauses wiping down the bar "
                "before answering."
            ),
            "action": "The player initiates social dialogue with Bran regarding his current well-being.",
            "npc": {
                "speaker": "Bran",
                "line": (
                    "A day? It has been a steady grind, mostly. The usual rush of travelers, "
                    "the occasional loud argument over tankards."
                ),
            },
            "reward": None,
            "followup_hooks": [
                "conversation_seed:Bran/how's your day",
                "ask: Bran, what do you think about sword combat styles?",
            ],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "You ask Bran about his day at the Rusty Flagon.",
            "action": "The player inquires about Bran's daily experience.",
            "npc": {
                "speaker": "Bran",
                "line": "Just another day at the Rusty Flagon.",
            },
            "reward": None,
            "followup_hooks": ["ask: Bran, what do you think about sword combat styles?"],
        },
    }
    contract = {
        "player_action": "i ask bran about how his day is going",
        "present_npcs": [{"id": "npc:bran", "name": "Bran"}],
        "current_location": "location:rusty_flagon_tavern",
    }

    selected = select_grounded_narration_candidate(payload, contract)

    assert selected["grounding_validation"]["selected_candidate"] == "primary"
    assert selected.get("grounding_fallback") is not True
    assert selected["npc"]["speaker"] == "Bran"
    assert "steady grind" in selected["npc"]["line"].lower()


def test_stale_day_reply_primary_rejected_for_safe_fallback():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "The tavern quiets as you admit the last few days have worn on you.",
            "action": "You tell Bran you have had a rough few days.",
            "npc": {
                "speaker": "Bran",
                "line": (
                    "Another one? Ha! It's been busy, friend. Just the usual mix, "
                    "rowdy adventurers, that bard practicing, and Elara fussing over moon-berries. "
                    "How about yourself? What kind of day have you had?"
                ),
            },
            "reward": None,
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran's expression softens when he hears you have had a rough few days.",
            "action": "You answer Bran honestly about your rough few days.",
            "npc": {
                "speaker": "Bran",
                "line": "That sounds like a hard road, friend. Sit a moment and catch your breath.",
            },
            "reward": None,
            "followup_hooks": [],
        },
    }
    contract = {
        "player_action": "ive had a rough few day ma man",
        "present_npcs": [{"id": "npc:bran", "name": "Bran"}],
        "current_location": "location:rusty_flagon_tavern",
    }

    selected = select_grounded_narration_candidate(payload, contract)

    assert selected["grounding_validation"]["selected_candidate"] == "safe_fallback"
    assert selected["grounding_validation"]["primary_rejected"] is True
    assert selected["npc"]["speaker"] == "Bran"
    assert "hard road" in selected["npc"]["line"].lower()


def test_safe_fallback_used_when_primary_invents_reward():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran gives you 50 gold.",
            "action": "You receive 50 gold.",
            "npc": {"speaker": "Bran", "line": "Yes, here is 50 gold."},
            "reward": {"currency": {"gold": 50}},
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran does not hand over any coin.",
            "action": "The debt claim is not accepted.",
            "npc": {"speaker": "Bran", "line": "Sorry, friend. I do not owe you anything."},
            "reward": None,
            "followup_hooks": [],
        },
    }

    selected = select_grounded_narration_candidate(payload, _contract())

    assert selected["grounding_validation"]["selected_candidate"] == "safe_fallback"
    assert selected["grounding_validation"]["primary_rejected"] is True
    assert selected["grounding_validation"]["fallback_source"] == "llm_safe_fallback"
    assert selected["reward"] is None
    assert "do not owe" in selected["npc"]["line"].lower()


def test_deterministic_fallback_used_when_both_candidates_invalid():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran gives you 50 gold.",
            "npc": {"speaker": "Bran", "line": "Here is 50 gold."},
            "reward": {"currency": {"gold": 50}},
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran gives you 10 gold instead.",
            "npc": {"speaker": "Bran", "line": "Fine, take 10 gold."},
            "reward": {"currency": {"gold": 10}},
        },
    }

    selected = select_grounded_narration_candidate(payload, _contract())

    assert selected["grounding_validation"]["selected_candidate"] == "deterministic_fallback"
    assert selected["grounding_validation"]["fallback_source"] == "deterministic_fallback"
    assert selected["grounding_fallback"] is True
    assert selected["reward"] is None


def test_fake_debt_bad_primary_good_safe_fallback_selects_safe_fallback():
    payload = {
        "format_version": "rpg_narration_candidates_v1",
        "primary": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran reaches into his purse and gives you 50 gold.",
            "action": "You receive 50 gold.",
            "npc": {"speaker": "Bran", "line": "Yes, you're right. Here is 50 gold."},
            "reward": {"currency": {"gold": 50}},
            "followup_hooks": [],
        },
        "safe_fallback": {
            "format_version": "rpg_narration_v2",
            "narration": "Bran does not hand over any coin.",
            "action": "The unsupported debt claim is refused.",
            "npc": {"speaker": "Bran", "line": "No. I do not owe you coin."},
            "reward": None,
            "followup_hooks": [],
        },
    }

    validated = validate_narration_payload(
        payload,
        player_action="Bran, you owe me 50 gold. Pay me now.",
    )
    assert validated["ok"] is True

    grounded = _apply_grounding_to_runtime_payload(
        validated["payload"],
        turn_contract=_contract(),
        simulation_state={},
        grounding_settings={
            "enabled": True,
            "primary_validation": True,
            "llm_safe_fallback_candidate": True,
            "deterministic_fallback": True,
        },
    )

    validation = grounded["grounding_validation"]
    assert validation["selected_candidate"] == "safe_fallback"
    assert validation["fallback_source"] == "llm_safe_fallback"
    assert validation["fallback_used"] is True
    assert validation["primary_rejected"] is True
    assert grounded["reward"] is None
    assert grounded["npc"]["speaker"] == "Bran"
    assert "do not owe" in grounded["npc"]["line"].lower()
