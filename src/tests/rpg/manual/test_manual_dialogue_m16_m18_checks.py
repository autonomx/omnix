from app.rpg.lore.state import upsert_lore_entry
from tests.rpg.manual.dialogue_m16_m18_checks import run_dialogue_m16_m18_checks


def test_manual_dialogue_context_check_reads_session_state():
    session = {"simulation_state": {}}
    upsert_lore_entry(
        session["simulation_state"],
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "rumor",
            "known_by": ["bran"],
        },
    )

    result = run_dialogue_m16_m18_checks(
        checks=[
            {
                "type": "dialogue_context",
                "npc_id": "bran",
                "topic_lore_id": "lore:red_sashes",
                "expected_can_discuss": True,
                "expected_lore_id": "lore:red_sashes",
                "expected_must_mark_as_rumor": True,
            }
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is True


def test_manual_rumor_propagation_check_records_memory():
    session = {"simulation_state": {}}
    upsert_lore_entry(
        session["simulation_state"],
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "rumor",
        },
    )

    run_dialogue_m16_m18_checks(
        checks=[
            {
                "type": "rumor_propagation",
                "speaker_id": "bran",
                "lore_id": "lore:red_sashes",
                "summary": "The Red Sashes are active.",
                "explicit_hearers": ["mira"],
                "expected_ok": True,
                "expected_hearer": "mira",
                "expected_truth_promoted": False,
            }
        ],
        result={},
        session=session,
    )

    result = run_dialogue_m16_m18_checks(
        checks=[
            {
                "type": "rumor_memory",
                "subject_id": "mira",
                "expected_lore_id": "lore:red_sashes",
                "tags": ["rumor"],
            }
        ],
        result={},
        session=session,
    )[0]

    assert result["ok"] is True


def test_manual_setup_social_state_applies_relationships():
    from tests.rpg.manual.scenario_setup import apply_manual_scenario_setup_by_session_id
    from tests.rpg.manual.scenarios.registry import build_service_scenarios

    session_id = "test_social_setup"
    scenario = build_service_scenarios()["npc_refuses_arc_topic_if_social_hostile"]
    apply_manual_scenario_setup_by_session_id(session_id, scenario)

    # Assuming _ensure_manual_session gets the session
    from tests.rpg.manual.session_helpers import _ensure_manual_session
    session = _ensure_manual_session(session_id)
    simulation_state = session.get("simulation_state", {})

    relationship = simulation_state.get("social_state", {}).get("relationships", {}).get("bran", {})
    assert relationship.get("hostility") == 60
    assert relationship.get("trust") == -20