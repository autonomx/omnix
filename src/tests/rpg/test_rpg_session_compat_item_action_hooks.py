from __future__ import annotations

from typing import Any

from app.platform import rpg_session_compat
from app.rpg.session import service


def _session() -> dict[str, Any]:
    return {
        "manifest": {"session_id": "rpg_test", "title": "Test"},
        "state": {
            "session_id": "rpg_test",
            "current_turn": 1,
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


def test_item_action_compat_runs_item_hooks_after_real_dispatcher_action(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "item_action",
            "session_id": "rpg_test",
            "item_action": {"action": "effect", "item_name": "Calm Focus", "effect_id": "steady"},
            "diagnostics_interval": 99,
            "maintenance_interval": 99,
            "report_interval": 99,
            "objective_limit": 2,
        }
    )

    assert result["ok"] is True
    assert result["session_action"] == "effect"
    assert result["item_hook_result"]["skipped"] is False
    assert result["item_hook_result"]["action"] == "effect"
    assert result["game"] is saved[0]["state"]
    assert result["game"]["player"]["resources"]["mana"]["current"] == 5
    assert result["game"]["mechanics"]["item_session_action_hook_traces"][0]["action"] == "effect"
    assert result["game"]["mechanics"]["item_turn_hook_traces"]


def test_item_command_compat_runs_item_hooks_after_real_command(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "item_command",
            "session_id": "rpg_test",
            "command": "use Calm Focus",
            "diagnostics_interval": 99,
            "maintenance_interval": 99,
            "report_interval": 99,
        }
    )

    assert result["ok"] is True
    assert result["normalized_action"]["action"] == "effect"
    assert result["item_hook_result"]["skipped"] is False
    assert result["game"] is saved[0]["state"]
    assert result["game"]["mechanics"]["item_command_traces"]
    assert result["game"]["mechanics"]["item_session_action_hook_traces"][0]["action"] == "effect"


def test_item_command_compat_does_not_save_unsupported_command_with_hooks(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)

    result = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_command", "session_id": "rpg_test", "command": "dance"}
    )

    assert result == {"session_id": "rpg_test", "ok": False, "error": "unsupported_item_command", "command": "dance"}
    assert saved == []
