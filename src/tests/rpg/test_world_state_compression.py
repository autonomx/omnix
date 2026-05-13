from app.rpg.state.world_state_compression import (
    compact_event_history,
    compress_world_state_snapshot,
    expire_world_signals,
)


def test_expire_world_signals_uses_ttl():
    result = expire_world_signals(
        world_signals=[
            {"id": "old", "turn": 1, "ttl_turns": 5},
            {"id": "new", "turn": 9, "ttl_turns": 5},
        ],
        current_turn=10,
    )

    assert result["expired_count"] == 1
    assert result["active_count"] == 1
    assert result["expired"][0]["id"] == "old"


def test_compact_event_history_keeps_recent_and_important():
    result = compact_event_history(
        events=[
            {"turn": 1, "summary": "old low", "importance": 0},
            {"turn": 2, "summary": "old important", "importance": 5},
            {"turn": 99, "summary": "recent", "importance": 0},
        ],
        current_turn=100,
        keep_recent_turns=10,
        keep_recent_count=10,
        keep_important_count=1,
    )

    kept = result["kept"]
    summaries = {row["summary"] for row in kept}

    assert "recent" in summaries
    assert "old important" in summaries
    assert "old low" not in summaries


def test_compress_world_state_snapshot_returns_budget():
    result = compress_world_state_snapshot(
        state={
            "story_arcs": {
                "arc:a": {
                    "arc_id": "arc:a",
                    "history": [{"turn": i, "summary": str(i)} for i in range(50)],
                }
            },
            "world_signals": [{"id": "old", "turn": 1, "ttl_turns": 5}],
            "faction_reputation": {},
            "npc_memory_events": [],
        },
        current_turn=100,
    )

    assert result["ok"] is True
    assert result["state_budget_summary"]["ok"] is True
    assert result["world_signals"]["expired_count"] == 1