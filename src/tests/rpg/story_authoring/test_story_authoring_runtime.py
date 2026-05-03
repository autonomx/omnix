import json

from app.rpg.story_authoring.runtime import author_story_proposal
from app.rpg.story_packs.registry import get_imported_story_pack


def _valid_proposal():
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "authored_bandit_pack",
        "title": "Authored Bandit Pack",
        "lore_entries": [
            {
                "lore_id": "lore:authored_red_sashes",
                "title": "Authored Red Sashes",
                "truth_status": "rumor",
            }
        ],
        "story_arcs": [
            {
                "arc_id": "arc:authored_bandit_pressure",
                "title": "Authored Bandit Pressure",
                "status": "active",
                "stage": "rumors",
                "pressure": 10,
                "linked_lore": ["lore:authored_red_sashes"],
            }
        ],
        "story_events": [],
        "escalation_rules": [],
    }


def test_author_story_proposal_validates_override_without_import():
    simulation_state = {}

    result = author_story_proposal(
        simulation_state,
        authoring_goal="Create a small bandit rumor pack.",
        llm_text_override=json.dumps(_valid_proposal()),
        import_if_valid=False,
        turn_index=1,
    )

    assert result["ok"] is True
    assert result["reason"] == "validated"
    assert simulation_state["story_authoring_state"]["attempts"][0]["validation_ok"] is True
    assert "story_pack_state" not in simulation_state


def test_author_story_proposal_imports_when_enabled():
    simulation_state = {}

    result = author_story_proposal(
        simulation_state,
        authoring_goal="Create a small bandit rumor pack.",
        llm_text_override=json.dumps(_valid_proposal()),
        import_if_valid=True,
        turn_index=1,
    )

    assert result["ok"] is True
    assert result["reason"] == "imported"
    pack_id = result["import_result"]["pack_id"]
    assert get_imported_story_pack(simulation_state, pack_id) is not None
    assert simulation_state["story_authoring_state"]["attempts"][0]["import_ok"] is True


def test_author_story_proposal_rejects_invalid_json():
    simulation_state = {}

    result = author_story_proposal(
        simulation_state,
        authoring_goal="Create a bad pack.",
        llm_text_override="{bad json",
        import_if_valid=True,
        turn_index=1,
    )

    assert result["ok"] is False
    assert result["reason"] == "parse_failed"
    assert simulation_state["story_authoring_state"]["attempts"][0]["status"] == "parse_failed"
    assert "story_pack_state" not in simulation_state


def test_author_story_proposal_rejects_validator_failure_without_import():
    simulation_state = {}
    invalid = _valid_proposal()
    invalid["story_events"] = [
        {"event_id": "event:bad", "arc_id": "arc:missing", "effects": []}
    ]

    result = author_story_proposal(
        simulation_state,
        authoring_goal="Create an invalid pack.",
        llm_text_override=json.dumps(invalid),
        import_if_valid=True,
        turn_index=1,
    )

    assert result["ok"] is False
    assert result["reason"] == "validation_failed"
    assert simulation_state["story_authoring_state"]["attempts"][0]["validation_ok"] is False
    assert "story_pack_state" not in simulation_state


def test_story_authoring_attempt_history_bounded():
    simulation_state = {}
    for i in range(130):
        proposal = _valid_proposal()
        proposal["proposal_id"] = f"authored_pack_{i}"
        proposal["lore_entries"][0]["lore_id"] = f"lore:x_{i}"
        proposal["story_arcs"][0]["arc_id"] = f"arc:x_{i}"
        proposal["story_arcs"][0]["linked_lore"] = [f"lore:x_{i}"]
        author_story_proposal(
            simulation_state,
            authoring_goal=f"Create pack {i}.",
            llm_text_override=json.dumps(proposal),
            import_if_valid=False,
            turn_index=i,
        )

    assert len(simulation_state["story_authoring_state"]["attempts"]) == 100