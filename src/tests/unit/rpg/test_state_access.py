"""AL020: a document's sections are read through the accessors that name their keys, which change nothing else."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app.apps.rpg.foundation.state.access import ACCESSORS, player_state_of, simulation_state_of

ROOT = Path(__file__).resolve().parents[4]


def test_an_accessor_returns_what_its_holder_keeps_as_it_keeps_it() -> None:
    player = {"hp": 3}
    simulation = {"player_state": player}
    document = {"simulation_state": simulation}
    assert simulation_state_of(document) is simulation and player_state_of(simulation_state_of(document)) is player
    assert simulation_state_of({}) is None and simulation_state_of({"simulation_state": None}) is None
    assert player_state_of("not a mapping") is None


def test_there_is_an_accessor_for_every_section_key_the_lint_watches(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))  # the lint imports its sibling modules
    spec = importlib.util.spec_from_file_location("omnix_architecture_lint_for_access", ROOT / "scripts/architecture_lint.py")
    lint = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(lint)
    assert set(ACCESSORS) == set(lint._RPG_SECTION_KEYS)


def test_a_field_accessor_returns_its_own_key() -> None:
    from app.apps.rpg.foundation.state.access import FIELD_ACCESSORS

    for key, accessor in FIELD_ACCESSORS.items():
        marker = object()
        assert accessor({key: marker}) is marker and accessor({}) is None and accessor(None) is None


def test_the_turn_count_has_one_reader_with_one_precedence() -> None:
    from app.apps.rpg.foundation.state.access import turn_count_of
    from app.apps.rpg.foundation.state.changes import TimeAdvanced, TurnCounted
    from app.apps.rpg.session.turn.resolution import next_turn, timed_changes

    assert turn_count_of({"state": {"turn_count": 4}, "manifest": {"turn_count": 2}}) == 4  # the sheet's first
    assert turn_count_of({"state": {}, "manifest": {"turn_count": 2}}) == 2  # the manifest's for a sheet without one
    assert turn_count_of({}) == 0 and turn_count_of(None) == 0
    opened = {"state": {"turn_count": 7}}  # an opening already under way sets the sheet's alone
    assert next_turn(opened) == TurnCounted(turn_count=8)
    assert timed_changes(opened, [], 25) == [TurnCounted(turn_count=8), TimeAdvanced(ticks=3, minutes=25)]
    assert timed_changes(opened, [], 0) == [TurnCounted(turn_count=8)]


def test_no_rule_reads_the_turn_count_by_its_key() -> None:
    """The turn path reads the count through ``turn_count_of``; a second reader would bring back its own
    precedence (the sheet's or the manifest's, ``turn_count`` or ``current_turn``)."""
    package = ROOT / "src" / "app" / "apps" / "rpg"
    readers = [
        f"{path.relative_to(package)}:{number}"
        for folder in ("rules", "session/turn", "world", "narration/game_master")
        for path in sorted((package / folder).rglob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if '.get("turn_count")' in line or '.get("current_turn")' in line
    ]
    assert readers == []
