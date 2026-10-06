from __future__ import annotations

import pytest

from app.conversation import legacy_sessions


def test_legacy_session_bridge_requires_installed_durable_authority(monkeypatch) -> None:
    monkeypatch.setattr(legacy_sessions, "_load", None)
    monkeypatch.setattr(legacy_sessions, "_save", None)
    monkeypatch.setattr(legacy_sessions, "_update", None)

    with pytest.raises(RuntimeError, match="durable legacy session authority"):
        legacy_sessions.load_sessions()
    with pytest.raises(RuntimeError, match="durable legacy session authority"):
        legacy_sessions.write_legacy_session_state({"session": {}})
    with pytest.raises(RuntimeError, match="durable legacy session authority"):
        legacy_sessions.update_sessions(lambda sessions: sessions.clear())
