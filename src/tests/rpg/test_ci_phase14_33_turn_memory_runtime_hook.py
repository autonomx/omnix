from __future__ import annotations

from types import ModuleType

from app.rpg.session.turn_memory_runtime_hook import force_install_turn_memory_runtime_hook_for_tests
from tests.rpg.turn_memory_test_helpers import bran_result, memory_session


def test_runtime_hook_wraps_apply_turn_and_preserves_result() -> None:
    module = ModuleType("fake_interactive_memory_runtime")
    calls: list[tuple[str, str]] = []

    def apply_turn(session_id: str, player_input: str, **kwargs):
        calls.append((session_id, player_input))
        return bran_result(tick=3, player_input=player_input)

    module.apply_turn = apply_turn  # type: ignore[attr-defined]

    assert force_install_turn_memory_runtime_hook_for_tests(module) is True
    result = module.apply_turn(  # type: ignore[attr-defined]
        "session-memory-1",
        "Bran, my trail name is Red Fox.",
        session_override=memory_session(),
    )

    assert calls == [("session-memory-1", "Bran, my trail name is Red Fox.")]
    assert result["ok"] is True
    assert result["turn_memory_runtime_hook"]["attached"] is True
    assert result["turn_memory"]["written"]["facts"][0]["value"] == "Red Fox"


def test_runtime_hook_reports_noop_for_non_dict_results() -> None:
    module = ModuleType("fake_interactive_memory_runtime_non_dict")

    def apply_turn(*args, **kwargs):
        return "not-a-dict"

    module.apply_turn = apply_turn  # type: ignore[attr-defined]
    assert force_install_turn_memory_runtime_hook_for_tests(module) is True
    assert module.apply_turn("session-memory-1", "What now?") == "not-a-dict"  # type: ignore[attr-defined]
