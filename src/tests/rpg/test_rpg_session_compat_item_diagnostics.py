from __future__ import annotations

from typing import Any

from app.platform import rpg_session_compat
from app.rpg.session import item_diagnostics, item_state_maintenance, service


def _session() -> dict[str, Any]:
    return {
        "manifest": {"session_id": "rpg_test", "title": "Test"},
        "state": {
            "session_id": "rpg_test",
            "player": {"inventory": []},
            "mechanics": {},
        },
    }


def test_item_diagnostics_compat_builds_without_saving(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    seen: list[tuple[dict[str, Any], str | None, str, int, int]] = []

    def build_item_diagnostics(
        state: dict[str, Any],
        *,
        station: str | None = None,
        genre: str = "classic_fantasy",
        scenario_limit: int = 8,
        objective_limit: int = 8,
    ) -> dict[str, Any]:
        seen.append((state, station, genre, scenario_limit, objective_limit))
        return {"ok": True, "summary": {"coverage_score": 100}}

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)
    monkeypatch.setattr(item_diagnostics, "build_item_diagnostics", build_item_diagnostics)

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "item_diagnostics",
            "session_id": "rpg_test",
            "station": "quarry",
            "genre": "cozy_mystery",
            "scenario_limit": "3",
            "objective_limit": 4,
        }
    )

    assert result["ok"] is True
    assert result["session_id"] == "rpg_test"
    assert result["diagnostics"] == {"ok": True, "summary": {"coverage_score": 100}}
    assert result["game"]["session_id"] == "rpg_test"
    assert saved == []
    assert seen[0][1:] == ("quarry", "cozy_mystery", 3, 4)


def test_item_diagnostics_compat_records_and_saves_session(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []

    def record_item_diagnostics(
        state: dict[str, Any],
        *,
        station: str | None = None,
        genre: str = "classic_fantasy",
        scenario_limit: int = 8,
        objective_limit: int = 8,
    ) -> dict[str, Any]:
        state.setdefault("mechanics", {})["item_diagnostic_traces"] = [
            {"event": "item_diagnostics_recorded", "station": station, "genre": genre}
        ]
        return {"ok": True, "mechanics_trace": {"event": "item_diagnostics_recorded"}}

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)
    monkeypatch.setattr(item_diagnostics, "record_item_diagnostics", record_item_diagnostics)

    result = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_diagnostics", "session_id": "rpg_test", "record": True}
    )

    assert result["ok"] is True
    assert result["session"] is saved[0]
    assert result["game"] is saved[0]["state"]
    assert result["diagnostics"]["mechanics_trace"] == {"event": "item_diagnostics_recorded"}
    assert saved[0]["state"]["mechanics"]["item_diagnostic_traces"] == [
        {"event": "item_diagnostics_recorded", "station": None, "genre": "classic_fantasy"}
    ]


def test_item_maintenance_compat_dry_run_builds_without_saving(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    seen: list[tuple[int, int, bool]] = []

    def build_item_state_maintenance_plan(
        state: dict[str, Any],
        *,
        bucket_limit: int = 50,
        compaction_threshold: int = 50,
        include_report: bool = False,
    ) -> dict[str, Any]:
        seen.append((bucket_limit, compaction_threshold, include_report))
        return {"ok": True, "actions": ["audit"], "summary": {"audit_issue_count": 0}}

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)
    monkeypatch.setattr(
        item_state_maintenance,
        "build_item_state_maintenance_plan",
        build_item_state_maintenance_plan,
    )

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "item_maintenance",
            "session_id": "rpg_test",
            "dry_run": "true",
            "bucket_limit": "7",
            "record_report": True,
        }
    )

    assert result["ok"] is True
    assert result["maintenance"] == {"ok": True, "actions": ["audit"], "summary": {"audit_issue_count": 0}}
    assert result["game"]["session_id"] == "rpg_test"
    assert saved == []
    assert seen == [(7, 7, True)]


def test_item_maintenance_compat_runs_and_saves_session(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    seen: list[tuple[int, int, bool]] = []

    def run_item_state_maintenance(
        state: dict[str, Any],
        *,
        bucket_limit: int = 50,
        compaction_threshold: int = 50,
        record_report: bool = False,
    ) -> dict[str, Any]:
        seen.append((bucket_limit, compaction_threshold, record_report))
        state.setdefault("mechanics", {})["item_state_maintenance_traces"] = [
            {"event": "item_state_maintained"}
        ]
        return {"ok": True, "summary": {"report_recorded": record_report}}

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)
    monkeypatch.setattr(item_state_maintenance, "run_item_state_maintenance", run_item_state_maintenance)

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "item_maintenance",
            "session_id": "rpg_test",
            "bucket_limit": 6,
            "compaction_threshold": "9",
            "record_report": "yes",
        }
    )

    assert result["ok"] is True
    assert result["session"] is saved[0]
    assert result["game"] is saved[0]["state"]
    assert result["maintenance"] == {"ok": True, "summary": {"report_recorded": True}}
    assert saved[0]["state"]["mechanics"]["item_state_maintenance_traces"] == [
        {"event": "item_state_maintained"}
    ]
    assert seen == [(6, 9, True)]


def test_item_diagnostics_and_maintenance_compat_reject_missing_session(monkeypatch) -> None:
    monkeypatch.setattr(service, "load_session", lambda session_id: None)

    diagnostics = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_diagnostics", "session_id": "missing"}
    )
    maintenance = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_maintenance", "session_id": "missing"}
    )

    assert diagnostics == {"ok": False, "error": "session_not_found", "session_id": "missing"}
    assert maintenance == {"ok": False, "error": "session_not_found", "session_id": "missing"}


def test_item_diagnostics_and_maintenance_compat_require_session_id() -> None:
    diagnostics = rpg_session_compat.get_rpg_session_payload({"action": "item_diagnostics"})
    maintenance = rpg_session_compat.get_rpg_session_payload({"action": "item_maintenance"})

    assert diagnostics == {"ok": False, "error": "missing_session_id"}
    assert maintenance == {"ok": False, "error": "missing_session_id"}
