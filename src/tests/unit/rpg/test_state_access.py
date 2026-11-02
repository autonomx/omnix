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
