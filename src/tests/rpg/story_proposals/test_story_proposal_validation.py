from app.rpg.lore.state import upsert_lore_entry
from app.rpg.story_proposals.validation import validate_story_proposal


def _valid_pack():
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "proposal:red_sashes_intro",
        "title": "Red Sashes Intro",
        "lore_entries": [
            {
                "lore_id": "lore:red_sashes",
                "title": "The Red Sashes",
                "truth_status": "rumor",
                "tags": ["bandit"],
            }
        ],
        "story_arcs": [
            {
                "arc_id": "arc:bandit_pressure",
                "title": "Bandit Pressure",
                "status": "active",
                "stage": "rumors",
                "pressure": 20,
                "linked_lore": ["lore:red_sashes"],
            }
        ],
        "story_events": [
            {
                "event_id": "event:bandit_rumor_spreads",
                "arc_id": "arc:bandit_pressure",
                "kind": "rumor",
                "summary": "Rumors of bandits spread.",
                "effects": [
                    {"type": "arc_pressure_delta", "arc_id": "arc:bandit_pressure", "delta": 10}
                ],
            }
        ],
        "escalation_rules": [
            {
                "rule_id": "rule:bandit_warning",
                "arc_id": "arc:bandit_pressure",
                "priority": 70,
                "conditions": [
                    {
                        "type": "arc_pressure_at_least",
                        "arc_id": "arc:bandit_pressure",
                        "minimum": 50,
                    }
                ],
                "event": {
                    "event_id": "event:bandits_warn_bran",
                    "arc_id": "arc:bandit_pressure",
                    "effects": [
                        {"type": "arc_stage_set", "arc_id": "arc:bandit_pressure", "stage": "threat"}
                    ],
                },
            }
        ],
    }


def test_story_proposal_valid_pack_accepts():
    result = validate_story_proposal({}, _valid_pack())

    assert result["ok"] is True
    assert result["result_counts"] == {
        "lore_entries": 1,
        "story_arcs": 1,
        "story_events": 1,
        "escalation_rules": 1,
    }


def test_story_proposal_invalid_version_rejected():
    pack = _valid_pack()
    pack["proposal_version"] = "bad"

    result = validate_story_proposal({}, pack)

    assert result["ok"] is False
    assert any(row["reason"] == "unsupported_proposal_version" for row in result["errors"])


def test_story_proposal_unknown_effect_rejected():
    pack = _valid_pack()
    pack["story_events"][0]["effects"] = [{"type": "invent_gold", "amount": 999}]

    result = validate_story_proposal({}, pack)

    assert result["ok"] is False
    assert "unknown_effect_type" in str(result["errors"])


def test_story_proposal_unbounded_pressure_rejected():
    pack = _valid_pack()
    pack["story_events"][0]["effects"] = [
        {"type": "arc_pressure_delta", "arc_id": "arc:bandit_pressure", "delta": 999}
    ]

    result = validate_story_proposal({}, pack)

    assert result["ok"] is False
    assert "pressure_delta_out_of_bounds" in str(result["errors"])


def test_story_proposal_contradicts_true_lore_rejected():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {"lore_id": "lore:red_sashes", "title": "The Red Sashes", "truth_status": "true"},
    )
    pack = _valid_pack()
    pack["lore_entries"][0]["truth_status"] = "false"

    result = validate_story_proposal(simulation_state, pack)

    assert result["ok"] is False
    assert "contradicts_existing_true_lore" in str(result["errors"])


def test_story_proposal_secret_not_revealed_by_default():
    pack = _valid_pack()
    pack["lore_entries"][0]["truth_status"] = "secret"
    pack["lore_entries"][0]["revealed_to_player"] = True

    result = validate_story_proposal({}, pack)

    assert result["ok"] is False
    assert "secret_lore_revealed_by_default" in str(result["errors"])


def test_story_proposal_rumor_kept_as_rumor():
    result = validate_story_proposal({}, _valid_pack())

    lore = result["normalized"]["lore_entries"][0]
    assert result["ok"] is True
    assert lore["truth_status"] == "rumor"


def test_story_proposal_non_dict_rejected():
    result = validate_story_proposal({}, "not a dict")

    assert result["ok"] is False
    assert "invalid_proposal_json" in str(result["errors"])
    assert "unsupported_proposal_version" in str(result["errors"])
    assert result["result_counts"] == {
        "lore_entries": 0,
        "story_arcs": 0,
        "story_events": 0,
        "escalation_rules": 0,
    }
