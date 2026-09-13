from __future__ import annotations

from typing import Any

from app.platform import rpg_session_compat
from app.rpg.session import service


def _session() -> dict[str, Any]:
    return {
        "manifest": {"session_id": "rpg_test", "title": "Test"},
        "state": {
            "session_id": "rpg_test",
            "current_turn": 3,
            "player": {
                "inventory": [
                    {
                        "item_id": "calm_focus",
                        "name": "Calm Focus",
                        "item_type": "relic",
                        "quantity": 1,
                        "item_signals": [
                            {
                                "signal_id": "steady",
                                "op": "restore_resource",
                                "resource": "mana",
                                "amount": 3,
                                "consume": True,
                            }
                        ],
                    }
                ],
                "resources": {"mana": {"current": 2, "max": 8}},
            },
            "mechanics": {},
        },
    }


def test_item_resolve_compat_applies_text_item_command_with_hooks(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "item_resolve",
            "session_id": "rpg_test",
            "command": "use Calm Focus",
            "diagnostics_interval": 99,
            "maintenance_interval": 99,
            "report_interval": 99,
        }
    )

    assert result["ok"] is True
    assert result["handled"] is True
    assert result["skipped"] is False
    assert result["resolution_plan"]["input_kind"] == "command"
    assert result["game"] is saved[0]["state"]
    assert result["game"]["player"]["resources"]["mana"]["current"] == 5
    assert result["game"]["mechanics"]["item_session_action_hook_traces"][0]["action"] == "effect"


def test_item_resolve_compat_applies_nested_structured_input_with_hooks(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "item_resolve",
            "session_id": "rpg_test",
            "input": {
                "item_action": {
                    "action": "effect",
                    "item_name": "Calm Focus",
                    "effect_id": "steady",
                }
            },
            "diagnostics_interval": 99,
            "maintenance_interval": 99,
            "report_interval": 99,
        }
    )

    assert result["ok"] is True
    assert result["handled"] is True
    assert result["session_action"] == "effect"
    assert result["game"] is saved[0]["state"]
    assert result["game"]["mechanics"]["item_session_action_hook_traces"][0]["action"] == "effect"


def test_item_resolve_compat_skips_non_item_input_without_saving(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "item_resolve",
            "session_id": "rpg_test",
            "input": {"action": "travel", "destination": "Old Road"},
        }
    )

    assert result["ok"] is True
    assert result["handled"] is False
    assert result["skipped"] is True
    assert result["reason"] == "non_item_action"
    assert result["game"]["mechanics"] == {}
    assert saved == []


def test_item_resolve_compat_handles_missing_session_id() -> None:
    result = rpg_session_compat.get_rpg_session_payload({"action": "item_resolve"})

    assert result == {"ok": False, "error": "missing_session_id"}
