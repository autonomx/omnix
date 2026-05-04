from app.rpg.story_packs.activation import (
    activate_story_pack,
    build_story_pack_activation_snapshot,
    deactivate_story_pack,
    is_story_pack_active,
    list_active_story_pack_ids,
)
from app.rpg.story_packs.importer import import_story_pack


def _pack():
    return {
        "proposal_version": "story_proposal_v1",
        "proposal_type": "story_pack",
        "proposal_id": "activation_pack",
        "title": "Activation Pack",
        "lore_entries": [{"lore_id": "lore:activation", "title": "Activation", "truth_status": "rumor"}],
        "story_arcs": [
            {
                "arc_id": "arc:activation",
                "title": "Activation",
                "status": "active",
                "stage": "rumors",
                "pressure": 60,
                "linked_lore": ["lore:activation"],
            }
        ],
        "story_events": [],
        "escalation_rules": [],
    }


def test_imported_story_pack_starts_inactive():
    simulation_state = {}
    result = import_story_pack(simulation_state, _pack(), turn_index=1)

    assert result["ok"] is True
    assert is_story_pack_active(simulation_state, result["pack_id"]) is False


def test_activate_and_deactivate_story_pack():
    simulation_state = {}
    imported = import_story_pack(simulation_state, _pack(), turn_index=1)

    activated = activate_story_pack(simulation_state, imported["pack_id"], turn_index=2)
    deactivated = deactivate_story_pack(simulation_state, imported["pack_id"], turn_index=3)

    assert activated["ok"] is True
    assert activated["reason"] == "activated"
    assert deactivated["ok"] is True
    assert deactivated["reason"] == "deactivated"
    assert is_story_pack_active(simulation_state, imported["pack_id"]) is False


def test_activate_missing_story_pack_rejected():
    result = activate_story_pack({}, "storypack:missing", turn_index=1)

    assert result["ok"] is False
    assert result["reason"] == "story_pack_not_imported"


def test_list_active_story_pack_ids():
    simulation_state = {}
    imported = import_story_pack(simulation_state, _pack(), turn_index=1)
    activate_story_pack(simulation_state, imported["pack_id"], turn_index=2)

    assert list_active_story_pack_ids(simulation_state) == [imported["pack_id"]]


def test_story_pack_activation_snapshot_lists_status():
    simulation_state = {}
    imported = import_story_pack(simulation_state, _pack(), turn_index=1)

    snapshot = build_story_pack_activation_snapshot(simulation_state)

    assert snapshot["ok"] is True
    assert snapshot["packs"][0]["pack_id"] == imported["pack_id"]
    assert snapshot["packs"][0]["status"] == "inactive"