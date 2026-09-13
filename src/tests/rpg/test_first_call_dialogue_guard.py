from __future__ import annotations


def _advisory(line: str) -> dict:
    return {
        "action_type": "social_activity",
        "semantic_family": "social",
        "interaction_mode": "direct",
        "stateful": False,
        "needs_runtime_resolution": False,
        "target_id": "bran",
        "target_name": "Bran",
        "direct_response_gate": {"safe_to_display_now": True, "reason": "safe small talk"},
        "visible_response": {
            "narration": "",
            "npc": {"speaker": "Bran", "line": line},
        },
    }


def test_placeholder_npc_line_is_not_consumable() -> None:
    from app.rpg.session.first_call_dialogue_guard import install_first_call_dialogue_placeholder_guard
    from app.rpg.session import first_call_dialogue

    install_first_call_dialogue_placeholder_guard()

    selected = first_call_dialogue.choose_first_call_visible_response(
        semantic_advisory=_advisory(
            "[NPC Line will be filled upon runtime resolution, but the intent is to ask what he is doing.]"
        )
    )

    assert selected["consumable"] is False
    assert selected["reason"] == "no_safe_non_stateful_visible_response"
    assert selected["source"] == "first_call_dialogue_placeholder_guard_v1"
    assert selected["rejection_reasons"] == ["semantic_advisory:placeholder_npc_line"]


def test_real_npc_line_remains_consumable() -> None:
    from app.rpg.session.first_call_dialogue_guard import install_first_call_dialogue_placeholder_guard
    from app.rpg.session import first_call_dialogue

    install_first_call_dialogue_placeholder_guard()

    selected = first_call_dialogue.choose_first_call_visible_response(
        semantic_advisory=_advisory("Keeping the hearth warm and one ear on the road, as usual.")
    )

    assert selected["consumable"] is True
    assert selected["npc"]["line"] == "Keeping the hearth warm and one ear on the road, as usual."


def test_placeholder_line_predicate_is_strict() -> None:
    from app.rpg.session.first_call_dialogue_guard import is_placeholder_npc_line

    assert is_placeholder_npc_line("[NPC Line will be filled upon runtime resolution]")
    assert not is_placeholder_npc_line("I will answer after I check the ledger.")
    assert not is_placeholder_npc_line("runtime resolution is not a phrase Bran would say")
