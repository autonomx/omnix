"""An undo walks back to before the hero's last turn (rewind.md): past world ticks, upgrades and earlier rewinds."""
from __future__ import annotations

from app.apps.rpg.session.turn.rewind import undo_target


def _turn(resulting: int, **command) -> dict:
    return {"resulting_revision": resulting, "expected_revision": resulting - 1, "command": command}


def test_undo_skips_the_worlds_ticks_and_follows_earlier_rewinds() -> None:
    history = [  # newest first
        _turn(6, turn_kind="world_tick", player_input=""),
        _turn(5, turn_kind="player_text", player_input="go north"),
        _turn(4, turn_kind="world_tick", player_input=""),
        _turn(3, turn_kind="player_text", player_input="look"),
        _turn(2, kind="system"),
        _turn(1, turn_kind="player_text", player_input="wait"),
    ]
    assert undo_target(history, 6) == 4  # before "go north", past the tick after it
    rewound = [_turn(7, turn_kind="rewind", restored_revision=4, player_input="I undo my last turn."), *history]
    assert undo_target(rewound, 7) == 2  # again: before "look" (the tick at 4 skipped)
    assert undo_target([_turn(1, turn_kind="world_tick", player_input="")], 1) is None
