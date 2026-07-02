from __future__ import annotations

from app.assist_core.hermes_rpg_handoff_contract import hermes_rpg_handoff_contract


def test_hermes_rpg_handoff_contract_uses_canonical_path() -> None:
    payload = hermes_rpg_handoff_contract({"ok": True, "value": "check inventory"})

    assert payload["ok"] is True
    assert payload["command_text"] == "check inventory"
    assert payload["canonical_path"] == "rpg_command_input"
    assert payload["hermes_submits"] is False
    assert payload["state_changed"] is False
