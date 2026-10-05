from __future__ import annotations

from app.rpg.hermes import execution_ledger as ledger


def _record(command: str) -> dict:
    return ledger.hermes_rpg_execution_ledger_record(
        payload={"user_step": {"command_text": command}},
        config={"enabled": True},
        flow={"ok": True, "state_changed": True, "result": {}},
        readout={"status": "completed"},
    )


def test_execution_ledger_is_bounded_expiring_and_resettable(monkeypatch) -> None:
    now = 100.0
    monkeypatch.setattr(ledger, "_ledger_now", lambda: now)
    monkeypatch.setattr(ledger, "_MAX_LEDGER_ITEMS", 2)
    monkeypatch.setattr(ledger, "_LEDGER_TTL_SECONDS", 10.0)
    ledger.hermes_rpg_execution_ledger_reset()

    first = _record("first")
    second = _record("second")
    third = _record("third")

    recent = ledger.hermes_rpg_execution_ledger_recent(limit=20)
    assert recent["count"] == 2
    assert [item["command_text"] for item in recent["items"]] == ["third", "second"]
    assert len({first["execution_id"], second["execution_id"], third["execution_id"]}) == 3

    now += 11.0
    assert ledger.hermes_rpg_execution_ledger_recent()["items"] == []

    _record("after-expiry")
    ledger.hermes_rpg_execution_ledger_reset()
    assert ledger.hermes_rpg_execution_ledger_recent()["items"] == []
