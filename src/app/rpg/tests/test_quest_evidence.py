from app.rpg.session.public_state_bridge import synchronize_player_projections
from app.rpg.session.quest_evidence import apply_quest_evidence, authoritative_dialogue_clue
from app.rpg.session.runtime_part39 import _grounded_service_visible_response
from app.rpg.economy.service_resolver import resolve_service_turn
from app.rpg.session.service_runtime import service_action_from_result, service_authoritative_result


def _session() -> dict:
    return synchronize_player_projections(
        {
            "state": {
                "quests": [
                    {
                        "id": "tavern_rumor",
                        "title": "Rumor at the Rusty Flagon",
                        "status": "active",
                        "objective": "Ask Bran or the tavern regulars which rumor is true.",
                    }
                ]
            },
            "simulation_state": {},
            "runtime_state": {},
        }
    )


def test_registered_clue_advances_legacy_quest_data() -> None:
    session = _session()
    evidence = authoritative_dialogue_clue(
        quest_id="tavern_rumor",
        actor_ref="npc:Bran",
        clue_key="bran_rumor",
        tick=4,
    )

    transition = apply_quest_evidence(session["simulation_state"], evidence)
    projected = synchronize_player_projections(session)

    assert transition["applied"] is True
    assert transition["objective_id"] == "investigate_old_mill_road"
    assert "old mill road" in transition["objective"]
    assert projected["state"]["quests"][0]["objective"] == transition["objective"]


def test_quest_evidence_is_idempotent() -> None:
    session = _session()
    evidence = authoritative_dialogue_clue(
        quest_id="tavern_rumor",
        actor_ref="npc:Bran",
        clue_key="bran_rumor",
        tick=4,
    )

    first = apply_quest_evidence(session["simulation_state"], evidence)
    second = apply_quest_evidence(session["simulation_state"], evidence)

    assert first["applied"] is True
    assert second["applied"] is False
    assert second["reason"] == "quest_evidence_already_applied"
    assert second["evidence"]["clue_summary"] == evidence["clue_summary"]
    assert second["objective"] == "Investigate the strange lights near the old mill road."


def test_unregistered_actor_cannot_advance_quest() -> None:
    session = _session()
    evidence = authoritative_dialogue_clue(
        quest_id="tavern_rumor",
        actor_ref="npc:Elara",
        clue_key="bran_rumor",
        tick=4,
    )

    transition = apply_quest_evidence(session["simulation_state"], evidence)

    assert transition["applied"] is False
    assert transition["reason"] == "no_matching_quest_transition"


def test_registered_service_inquiry_emits_and_applies_quest_evidence() -> None:
    session = _session()
    service_result = resolve_service_turn(
        player_input="Bran, what rumors have you heard?",
        action={},
        resolved_action={},
        simulation_state=session["simulation_state"],
        runtime_state={},
    )
    action = service_action_from_result(
        "Bran, what rumors have you heard?",
        {},
        service_result,
    )

    authoritative = service_authoritative_result(session["simulation_state"], action)

    transition = authoritative["result"]["quest_transition"]
    assert transition["applied"] is True
    assert transition["evidence"]["source"] == "registered_quest_clue"
    assert "old mill road" in authoritative["simulation_state"]["quest_state"]["quests"][0]["objective"]
    visible = _grounded_service_visible_response(authoritative["result"])
    assert "frightened traveler" in visible["narration"]
    assert "strange lights" in visible["npc"]["line"]

    repeated = service_authoritative_result(authoritative["simulation_state"], action)
    repeated_transition = repeated["result"]["quest_transition"]
    repeated_visible = _grounded_service_visible_response(repeated["result"])
    assert repeated_transition["reason"] == "quest_evidence_already_applied"
    assert "frightened traveler" in repeated_visible["narration"]
    assert repeated_visible["npc"]["line"] == transition["evidence"]["clue_summary"]
