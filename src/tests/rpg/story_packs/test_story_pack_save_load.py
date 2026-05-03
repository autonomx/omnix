import json

from app.rpg.story_packs.importer import import_story_pack
from app.rpg.story_packs.registry import normalize_story_pack_state


def test_story_pack_state_json_roundtrip():
    simulation_state = {}
    result = import_story_pack(
        simulation_state,
        {
            "proposal_version": "story_proposal_v1",
            "proposal_type": "story_pack",
            "proposal_id": "tiny",
            "title": "Tiny Pack",
            "lore_entries": [{"lore_id": "lore:x", "title": "X"}],
            "story_arcs": [{"arc_id": "arc:x", "title": "X", "linked_lore": ["lore:x"]}],
            "story_events": [],
            "escalation_rules": [],
        },
    )

    encoded = json.dumps(simulation_state["story_pack_state"], sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_story_pack_state(decoded)

    assert result["ok"] is True
    assert result["pack_id"] in normalized["imported_packs"]