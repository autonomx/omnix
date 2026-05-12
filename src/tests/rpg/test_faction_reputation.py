from app.rpg.story.faction_reputation import apply_faction_deltas, build_faction_reputation_summary


def test_faction_reputation_applies_deltas_and_tiers():
    result = apply_faction_deltas(
        faction_state={},
        faction_deltas=[
            {"faction_id": "faction:locals", "delta": 2, "reason": "helped"},
            {"faction_id": "faction:enemy", "delta": -3, "reason": "opposed"},
        ],
        turn_index=5,
    )

    locals_row = result["factions"]["faction:locals"]
    enemy_row = result["factions"]["faction:enemy"]

    assert locals_row["reputation"] == 2
    assert locals_row["tier"] == "friendly"
    assert enemy_row["reputation"] == -3
    assert enemy_row["tier"] == "suspicious"

    summary = build_faction_reputation_summary(result["factions"])
    assert summary["ok"] is True
    assert summary["faction_count"] == 2