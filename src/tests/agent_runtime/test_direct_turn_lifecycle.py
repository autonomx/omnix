from __future__ import annotations

from pathlib import Path


def test_generalized_confirmation_uses_assistant_turn_coordinator() -> None:
    source = (Path(__file__).parents[2] / "app" / "chat" / "live_agent_store.py").read_text(encoding="utf-8")
    block = source.split("def _governed_execution_events", 1)[1].split("def _governed_rejection_events", 1)[0]
    assert "default_assistant_turn_coordinator" in block
    assert "coordinator.mark_streaming" in block
    assert "coordinator.is_cancelled" in block
