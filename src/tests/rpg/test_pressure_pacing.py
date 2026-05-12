from app.rpg.story.pressure_pacing import filter_pressure_events_for_pacing


def test_pressure_pacing_accepts_then_rejects_within_gap():
    first = filter_pressure_events_for_pacing(
        pressure_events=[
            {
                "type": "faction_pressure",
                "subtype": "watchers",
                "faction_id": "faction:test",
                "summary": "Watchers appear.",
            }
        ],
        world_signals=[
            {
                "id": "signal:test",
                "kind": "faction_pressure",
                "faction_id": "faction:test",
                "summary": "Signal.",
            }
        ],
        turn_index=10,
        emitted_key_turns={},
        min_gap_turns=10,
    )

    assert first["accepted_count"] == 1
    assert first["rejected_count"] == 0
    assert len(first["accepted_world_signals"]) == 1

    second = filter_pressure_events_for_pacing(
        pressure_events=[
            {
                "type": "faction_pressure",
                "subtype": "watchers",
                "faction_id": "faction:test",
                "summary": "Watchers appear.",
            }
        ],
        world_signals=[
            {
                "id": "signal:test",
                "kind": "faction_pressure",
                "faction_id": "faction:test",
                "summary": "Signal.",
            }
        ],
        turn_index=12,
        emitted_key_turns=first["emitted_key_turns"],
        min_gap_turns=10,
    )

    assert second["accepted_count"] == 0
    assert second["rejected_count"] == 1
    assert second["rejected_events"][0]["pacing_reject_reason"] == "min_gap_turns"


def test_pressure_pacing_caps_events_per_turn():
    result = filter_pressure_events_for_pacing(
        pressure_events=[
            {
                "type": "faction_pressure",
                "subtype": "watchers",
                "faction_id": "faction:a",
                "summary": "A.",
            },
            {
                "type": "faction_pressure",
                "subtype": "watchers",
                "faction_id": "faction:b",
                "summary": "B.",
            },
        ],
        world_signals=[],
        turn_index=10,
        emitted_key_turns={},
        max_events_per_turn=1,
    )

    assert result["accepted_count"] == 1
    assert result["rejected_count"] == 1
    assert result["rejected_events"][0]["pacing_reject_reason"] == "max_events_per_turn"


def test_pressure_pacing_rejects_repeated_raw_candidates():
    emitted = {}
    accepted = 0
    rejected = 0

    for turn in range(10, 16):
        result = filter_pressure_events_for_pacing(
            pressure_events=[
                {
                    "type": "faction_pressure",
                    "subtype": "watchers",
                    "faction_id": "faction:test",
                    "summary": "Watchers appear.",
                    "turn": turn,
                }
            ],
            world_signals=[
                {
                    "id": "signal:test",
                    "kind": "faction_pressure",
                    "faction_id": "faction:test",
                    "summary": "Signal.",
                }
            ],
            turn_index=turn,
            emitted_key_turns=emitted,
            min_gap_turns=12,
            max_events_per_turn=1,
        )
        emitted = result["emitted_key_turns"]
        accepted += result["accepted_count"]
        rejected += result["rejected_count"]

    assert accepted == 1
    assert rejected >= 1