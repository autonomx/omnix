from __future__ import annotations

from copy import deepcopy

import app.rpg.session.service as session_service
from app.rpg.map_package_bridge import (
    attach_map_state_to_package,
    packaged_map_state,
    restore_map_state_from_package,
)
from app.rpg.map_projection import initial_map_session_state
from app.rpg.map_release import persisted_map_state


def _session() -> dict[str, object]:
    return {
        "manifest": {"id": "session:package", "session_id": "session:package"},
        "state": {
            "session_id": "session:package",
            "player": {"location_id": "rusty_flagon_tavern"},
            "map_state": initial_map_session_state("rusty_flagon_tavern"),
        },
        "simulation_state": {"turn_index": 4},
        "runtime_state": {},
        "installed_packs": [],
    }


def test_package_bridge_round_trip_preserves_authoritative_map_state_only() -> None:
    session = _session()
    session["state"]["map_state"]["viewport"] = {"zoom": 2.5, "panX": -400, "panY": 20}
    package = attach_map_state_to_package({"simulation_state": {"turn_index": 4}}, session)

    assert packaged_map_state(package) == persisted_map_state(session)
    assert "viewport" not in packaged_map_state(package)

    restored = restore_map_state_from_package(
        {"manifest": session["manifest"], "state": {"player": {}}, "simulation_state": {}},
        package,
    )

    assert restored["state"]["map_state"] == persisted_map_state(session)
    assert restored["state"]["current_location_id"] == "rusty_flagon_tavern"
    assert restored["state"]["player"]["location_id"] == "rusty_flagon_tavern"


def test_package_bridge_does_not_mutate_source_payloads() -> None:
    session = _session()
    package = {"simulation_state": {"turn_index": 4}}
    original_session = deepcopy(session)
    original_package = deepcopy(package)

    exported = attach_map_state_to_package(package, session)
    restored = restore_map_state_from_package(session, exported)

    assert package == original_package
    assert session == original_session
    assert restored is not session


def test_session_service_export_import_wires_map_package_bridge(monkeypatch) -> None:
    session = _session()
    monkeypatch.setattr(session_service, "create_or_normalize_session", lambda value: value)
    monkeypatch.setattr(session_service, "assert_session_integrity", lambda value: None)
    monkeypatch.setattr(session_service, "assert_package_integrity", lambda value: None)
    monkeypatch.setattr(
        session_service,
        "session_to_package",
        lambda value: {"simulation_state": deepcopy(value["simulation_state"])},
    )

    package = session_service.export_session_as_package(deepcopy(session))
    monkeypatch.setattr(
        session_service,
        "package_to_session",
        lambda value: {
            "ok": True,
            "session": {
                "manifest": deepcopy(session["manifest"]),
                "state": {"player": {}},
                "simulation_state": deepcopy(value["simulation_state"]),
            },
        },
    )
    imported = session_service.import_session_from_package(package)

    assert packaged_map_state(package) == persisted_map_state(session)
    assert imported["ok"] is True
    assert imported["session"]["state"]["map_state"] == persisted_map_state(session)
    assert imported["session"]["state"]["player"]["location_id"] == "rusty_flagon_tavern"
