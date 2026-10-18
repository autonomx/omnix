"""The World Forge reads and writes campaign sessions only through the store it is given (R-3)."""
from __future__ import annotations

from typing import Any

from app.apps.rpg.genesis.contracts import CampaignSessions
from app.apps.rpg.genesis.forge.pipeline_adapter import attach_compiled_genesis_to_session
from app.apps.rpg.session.service import SESSION_CAMPAIGN_SESSIONS, SessionCampaignSessions


class _RecordingSessions(SessionCampaignSessions):
    def __init__(self, stored: dict[str, Any]) -> None:
        self.stored = stored
        self.calls: list[tuple[str, Any]] = []

    def load(self, session_id: str) -> dict[str, Any] | None:
        self.calls.append(("load", session_id))
        return dict(self.stored)

    def save(self, session: dict[str, Any], *, compact: bool = False) -> dict[str, Any]:
        self.calls.append(("save", compact))
        return {**session, "saved": True}


def _session() -> dict[str, Any]:
    return {"state": {"metadata": {}}, "runtime_state": {}, "setup_payload": {}, "manifest": {"id": "campaign:1"}}


def test_the_forge_loads_and_saves_through_the_given_store() -> None:
    sessions = _RecordingSessions(_session())
    compiled = {"compiler_version": "v1"}

    result = attach_compiled_genesis_to_session(
        {"ok": True, "session_id": "campaign:1"},
        compiled,
        {"active_goals": ["survive"]},
        sessions=sessions,
        compact_save=True,
    )

    assert sessions.calls == [("load", "campaign:1"), ("save", True)]
    assert result["session"]["saved"] is True
    assert result["game"]["compiled_genesis_snapshot"] == compiled


def test_an_unpersisted_attachment_never_touches_the_store() -> None:
    sessions = _RecordingSessions(_session())

    result = attach_compiled_genesis_to_session(
        {"ok": True, "session_id": "campaign:1", "session": _session()},
        {"compiler_version": "v1"},
        {},
        sessions=sessions,
        persist=False,
    )

    assert sessions.calls == []
    assert "saved" not in result["session"]


def test_the_session_store_implements_the_genesis_port() -> None:
    store: CampaignSessions = SESSION_CAMPAIGN_SESSIONS
    request = store.new_game_request({"campaign_template": "classic_fantasy"})
    assert request.campaign_template == "classic_fantasy"
