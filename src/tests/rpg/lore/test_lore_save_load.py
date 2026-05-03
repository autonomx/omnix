import json

from app.rpg.lore.state import (
    normalize_lore_state,
    reveal_lore_to_player,
    upsert_lore_entry,
)


def test_lore_state_json_roundtrip():
    simulation_state = {}
    upsert_lore_entry(
        simulation_state,
        {
            "lore_id": "lore:red_sashes",
            "title": "The Red Sashes",
            "truth_status": "rumor",
            "known_by": ["bran"],
            "tags": ["bandits"],
        },
    )
    reveal_lore_to_player(simulation_state, "lore:red_sashes")

    encoded = json.dumps(simulation_state["lore_state"], sort_keys=True)
    decoded = json.loads(encoded)
    normalized = normalize_lore_state(decoded)

    entry = normalized["entries"]["lore:red_sashes"]
    assert entry["revealed_to_player"] is True
    assert entry["truth_status"] == "rumor"
    assert entry["known_by"] == ["bran"]