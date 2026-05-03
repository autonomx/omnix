from __future__ import annotations

from tests.rpg.manual.session_helpers import (
    _ensure_manual_session,
    _save_manual_session_for_test,
)


def test_ensure_manual_session_creates_new_manual_session():
    session_id = "manual_service_test_spatial_session_helpers"

    session = _ensure_manual_session(session_id)

    assert isinstance(session, dict)
    assert session
    assert session.get("session_id") == session_id or session.get("id") == session_id
    assert isinstance(session.get("simulation_state"), dict)
    assert isinstance(session.get("runtime_state"), dict)


def test_save_and_reload_manual_session_preserves_simulation_state():
    session_id = "manual_service_test_spatial_session_reload"

    session = _ensure_manual_session(session_id)
    session.setdefault("simulation_state", {})["probe_value"] = "ok"
    _save_manual_session_for_test(session_id, session)

    reloaded = _ensure_manual_session(session_id)

    assert isinstance(reloaded.get("simulation_state"), dict)
    assert reloaded["simulation_state"].get("probe_value") == "ok"