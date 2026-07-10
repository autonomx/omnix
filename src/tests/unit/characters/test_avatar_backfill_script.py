from __future__ import annotations

import sys
import urllib.error

import pytest

from scripts import backfill_character_avatars


def test_backfill_uses_running_launcher_gateway_by_default(monkeypatch) -> None:
    requests: list[str] = []

    def fake_request(url: str, **_kwargs):
        requests.append(url)
        return {"items": []}

    monkeypatch.setattr(backfill_character_avatars, "_json_request", fake_request)
    monkeypatch.setattr(sys, "argv", ["backfill_character_avatars.py", "--no-wait"])

    assert backfill_character_avatars.main() == 0
    assert requests == ["http://127.0.0.1:8000/api/characters/backfill-cloned-voices"]


def test_backfill_connection_error_names_recovery_command(monkeypatch) -> None:
    def refused(*_args, **_kwargs):
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    monkeypatch.setattr(backfill_character_avatars.urllib.request, "urlopen", refused)

    with pytest.raises(RuntimeError, match=r"start_all\.bat"):
        backfill_character_avatars._json_request("http://127.0.0.1:8000/api/health")
