from __future__ import annotations

from app.rpg.session.recent_memory import add_recent_memory, recent_memory


def test_recent_memory_tracks_turn_and_dialogue() -> None:
    session = add_recent_memory(
        {"runtime_state": {}},
        player_input="Bran, my trail name is Red Fox.",
        npc_id="npc:bran",
        npc_line="I'll remember that.",
    )
    memory = recent_memory(session)
    assert memory["version"] == "recent_memory_v1"
    assert memory["dialogue"][0]["npc_id"] == "npc:bran"


def test_recent_memory_keeps_bounded_recent_turns() -> None:
    session: dict[str, object] = {"runtime_state": {}}
    for index in range(14):
        session = add_recent_memory(session, player_input=f"turn {index}")
    assert recent_memory(session)["turns"][0]["player_input"] == "turn 2"
