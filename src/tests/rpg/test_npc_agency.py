from app.rpg.npc.npc_agency import NPCAgencyRule, emit_npc_agency_events


def test_npc_agency_emits_when_schedule_arc_and_faction_match():
    result = emit_npc_agency_events(
        state={
            "npc_presence": {
                "npc:test": {
                    "location_id": "scene:test",
                    "activity": "watching",
                }
            },
            "story_arcs": {
                "arc:test": {
                    "current_stage": "active_stage",
                }
            },
            "faction_reputation": {
                "faction:test": {
                    "tier": "hostile",
                    "reputation": -5,
                }
            },
        },
        turn_index=10,
        rules=[
            NPCAgencyRule(
                id="agency:test",
                npc_id="npc:test",
                required_location_id="scene:test",
                required_arc_stage=("arc:test", "active_stage"),
                required_faction_tier=("faction:test", "suspicious"),
                event={"summary": "NPC acts."},
                world_signal={"id": "signal:test", "summary": "Signal."},
                memory_event={"summary": "Memory.", "importance": 2},
            )
        ],
    )

    assert result["event_count"] == 1
    assert result["events"][0]["npc_id"] == "npc:test"
    assert len(result["world_signals"]) == 1
    assert len(result["memory_events"]) == 1


def test_npc_agency_respects_cooldown():
    first = emit_npc_agency_events(
        state={
            "npc_presence": {
                "npc:test": {
                    "location_id": "scene:test",
                    "activity": "watching",
                }
            }
        },
        turn_index=10,
        rules=[
            NPCAgencyRule(
                id="agency:test",
                npc_id="npc:test",
                required_location_id="scene:test",
                cooldown_turns=10,
                event={"summary": "NPC acts."},
            )
        ],
    )

    second = emit_npc_agency_events(
        state={
            "npc_presence": {
                "npc:test": {
                    "location_id": "scene:test",
                    "activity": "watching",
                }
            }
        },
        turn_index=12,
        rules=[
            NPCAgencyRule(
                id="agency:test",
                npc_id="npc:test",
                required_location_id="scene:test",
                cooldown_turns=10,
                event={"summary": "NPC acts."},
            )
        ],
        last_emitted_turn_by_rule=first["last_emitted_turn_by_rule"],
    )

    assert first["event_count"] == 1
    assert second["event_count"] == 0