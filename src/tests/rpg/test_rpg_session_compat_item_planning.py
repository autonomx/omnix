from __future__ import annotations

from typing import Any

from app.platform import rpg_session_compat
from app.rpg.session import item_objectives, item_scenarios, service


def _session() -> dict[str, Any]:
    return {
        "manifest": {"session_id": "rpg_test", "title": "Test"},
        "state": {
            "session_id": "rpg_test",
            "player": {"inventory": []},
            "mechanics": {},
        },
    }


def test_item_objectives_compat_builds_without_saving(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    seen: list[tuple[dict[str, Any], str | None, str, int]] = []

    def build_item_objectives(
        state: dict[str, Any],
        *,
        station: str | None = None,
        genre: str = "classic_fantasy",
        limit: int = 6,
    ) -> dict[str, Any]:
        seen.append((state, station, genre, limit))
        return {"objectives": [{"objective_id": "report:item"}], "summary": {"objective_count": 1}}

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)
    monkeypatch.setattr(item_objectives, "build_item_objectives", build_item_objectives)

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "item_objectives",
            "session_id": "rpg_test",
            "station": "forge",
            "genre": "cozy_mystery",
            "objective_limit": "3",
        }
    )

    assert result["ok"] is True
    assert result["session_id"] == "rpg_test"
    assert result["objectives"] == {
        "objectives": [{"objective_id": "report:item"}],
        "summary": {"objective_count": 1},
    }
    assert result["game"]["session_id"] == "rpg_test"
    assert saved == []
    assert seen[0][1:] == ("forge", "cozy_mystery", 3)


def test_item_scenario_compat_builds_plan_without_saving(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    seen: list[tuple[str | None, str, int, bool]] = []

    def build_item_scenario_plan(
        state: dict[str, Any],
        *,
        station: str | None = None,
        genre: str = "classic_fantasy",
        limit: int = 8,
        include_status_steps: bool = True,
    ) -> dict[str, Any]:
        seen.append((station, genre, limit, include_status_steps))
        return {"steps": [{"step_id": "report:item"}], "summary": {"step_count": 1}}

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)
    monkeypatch.setattr(item_scenarios, "build_item_scenario_plan", build_item_scenario_plan)

    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "item_scenario",
            "session_id": "rpg_test",
            "station": "market",
            "genre": "classic_fantasy",
            "scenario_limit": "5",
            "include_status_steps": False,
        }
    )

    assert result["ok"] is True
    assert result["scenario"] == {"steps": [{"step_id": "report:item"}], "summary": {"step_count": 1}}
    assert result["game"]["session_id"] == "rpg_test"
    assert saved == []
    assert seen == [("market", "classic_fantasy", 5, False)]


def test_item_scenario_compat_runs_and_saves_session(monkeypatch) -> None:
    saved: list[dict[str, Any]] = []
    seen: list[tuple[list[dict[str, Any]] | None, str | None, str, int, str]] = []

    def run_item_scenario(
        state: dict[str, Any],
        *,
        steps: list[dict[str, Any]] | None = None,
        station: str | None = None,
        genre: str = "classic_fantasy",
        limit: int = 8,
        source: str = "item_scenario",
    ) -> dict[str, Any]:
        seen.append((steps, station, genre, limit, source))
        state.setdefault("mechanics", {})["item_scenario_traces"] = [
            {"event": "item_scenario_run", "source": source}
        ]
        return {"ok": True, "summary": {"ok_count": 1}}

    monkeypatch.setattr(service, "load_session", lambda session_id: _session())
    monkeypatch.setattr(service, "save_session", lambda session, *, compact=False: saved.append(session) or session)
    monkeypatch.setattr(item_scenarios, "run_item_scenario", run_item_scenario)

    step = {"step_id": "report:item", "action": {"action": "report"}, "executable": True}
    result = rpg_session_compat.get_rpg_session_payload(
        {
            "action": "item_scenario",
            "session_id": "rpg_test",
            "run": "yes",
            "steps": [step],
            "source": "compat_test",
            "limit": "2",
        }
    )

    assert result["ok"] is True
    assert result["session"] is saved[0]
    assert result["game"] is saved[0]["state"]
    assert result["scenario"] == {"ok": True, "summary": {"ok_count": 1}}
    assert saved[0]["state"]["mechanics"]["item_scenario_traces"] == [
        {"event": "item_scenario_run", "source": "compat_test"}
    ]
    assert seen == [([step], None, "classic_fantasy", 2, "compat_test")]


def test_item_planning_compat_rejects_missing_session(monkeypatch) -> None:
    monkeypatch.setattr(service, "load_session", lambda session_id: None)

    objectives = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_objectives", "session_id": "missing"}
    )
    scenario = rpg_session_compat.get_rpg_session_payload(
        {"action": "item_scenario", "session_id": "missing"}
    )

    assert objectives == {"ok": False, "error": "session_not_found", "session_id": "missing"}
    assert scenario == {"ok": False, "error": "session_not_found", "session_id": "missing"}


def test_item_planning_compat_requires_session_id() -> None:
    objectives = rpg_session_compat.get_rpg_session_payload({"action": "item_objectives"})
    scenario = rpg_session_compat.get_rpg_session_payload({"action": "item_scenario"})

    assert objectives == {"ok": False, "error": "missing_session_id"}
    assert scenario == {"ok": False, "error": "missing_session_id"}
