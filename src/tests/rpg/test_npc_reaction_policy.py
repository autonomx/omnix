from app.rpg.npc.npc_reaction_policy import NPCReactionRule, emit_npc_reactions


def test_npc_reaction_emits_when_present_and_consequence_matches():
    result = emit_npc_reactions(
        state={
            "npc_presence": {
                "npc:test": {"location_id": "scene:test"}
            },
            "faction_consequence_events": [
                {"subtype": "retaliation"}
            ],
        },
        turn_index=30,
        rules=[
            NPCReactionRule(
                id="npc_reaction:test",
                npc_id="npc:test",
                reaction_kind="warns",
                required_location_id="scene:test",
                required_consequence_kind="retaliation",
                event={"summary": "NPC reacts."},
                memory_event={"summary": "NPC remembers.", "importance": 2},
                world_signal={"id": "signal:test", "summary": "NPC signal."},
            )
        ],
    )

    assert result["event_count"] == 1
    assert result["events"][0]["npc_id"] == "npc:test"
    assert result["memory_events"]
    assert result["world_signals"]


def test_npc_reaction_requires_presence_location():
    result = emit_npc_reactions(
        state={
            "npc_presence": {
                "npc:test": {"location_id": "scene:elsewhere"}
            },
            "faction_consequence_events": [
                {"subtype": "retaliation"}
            ],
        },
        turn_index=30,
        rules=[
            NPCReactionRule(
                id="npc_reaction:test",
                npc_id="npc:test",
                reaction_kind="warns",
                required_location_id="scene:test",
                required_consequence_kind="retaliation",
            )
        ],
    )

    assert result["event_count"] == 0