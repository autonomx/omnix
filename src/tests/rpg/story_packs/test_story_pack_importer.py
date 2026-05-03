from app.rpg.lore.state import get_lore_entry, upsert_lore_entry
from app.rpg.story_arcs.state import get_story_arc
from app.rpg.story_packs.definition_registries import (
    get_escalation_rule_definition,
    get_story_event_definition,
)
from app.rpg.story_packs.importer import import_story_pack
from app.rpg.story_packs.registry import get_imported_story_pack


def _valid_pack():
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "red_sashes_intro",
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


def test_story_pack_import_adds_lore_arcs_events_rules():
    simulation_state = {}
    result = import_story_pack(simulation_state, _valid_pack(), turn_index=3)

    assert result["ok"] is True
    assert get_lore_entry(simulation_state, "lore:red_sashes")["truth_status"] == "rumor"
    assert get_story_arc(simulation_state, "arc:bandit_pressure")["stage"] == "rumors"
    assert get_story_event_definition(simulation_state, "event:bandit_rumor_spreads") is not None
    assert get_escalation_rule_definition(simulation_state, "rule:bandit_warning") is not None
    assert get_imported_story_pack(simulation_state, result["pack_id"]) is not None


def test_story_pack_import_is_idempotent():
    simulation_state = {}
    first = import_story_pack(simulation_state, _valid_pack(), turn_index=3)
    second = import_story_pack(simulation_state, _valid_pack(), turn_index=4)

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["reason"] == "already_imported"
    assert len(simulation_state["story_pack_state"]["imported_packs"]) == 1


def test_story_pack_import_does_not_overwrite_existing_true_lore():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "true",
        },
    )
    pack = _valid_pack()
    pack["lore_entries"][0]["truth_status"] = "false"

    result = import_story_pack(simulation_state, pack)

    assert result["ok"] is False
    assert result["reason"] == "validation_failed"
    assert get_lore_entry(simulation_state, "lore:red_sashes")["truth_status"] == "true"


def test_story_pack_can_seed_starter_quest():
    simulation_state = {}
    pack = _valid_pack()
    pack["starter_quests"] = [
        {
            "action": "start",
            "quest_id": "quest:stop_red_sashes",
            "stage": "investigate",
        }
    ]

    result = import_story_pack(simulation_state, pack, turn_index=5)

    assert result["ok"] is True
    imported = get_imported_story_pack(simulation_state, result["pack_id"])
    assert "quest:stop_red_sashes" in imported["quest_ids"]
    assert simulation_state["quest_state"]["quests"]["quest:stop_red_sashes"]["stage"] == "investigate"