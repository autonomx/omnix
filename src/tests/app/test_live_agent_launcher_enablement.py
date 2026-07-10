from __future__ import annotations

from pathlib import Path


def test_windows_launcher_enables_proposal_only_live_agent_pilot() -> None:
    root = Path(__file__).resolve().parents[3]
    source = (root / "start_all.bat").read_text(encoding="utf-8")

    assert 'if not defined HERMES_ENABLED set "HERMES_ENABLED=1"' in source
    assert 'if not defined OMNIX_LIVE_AGENT_ENABLED set "OMNIX_LIVE_AGENT_ENABLED=1"' in source
    assert (
        'if not defined OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED '
        'set "OMNIX_LIVE_AGENT_AUTO_ROUTE_ENABLED=1"'
    ) in source
    assert (
        'if not defined OMNIX_LIVE_AGENT_REQUIRE_HERMES '
        'set "OMNIX_LIVE_AGENT_REQUIRE_HERMES=1"'
    ) in source
    assert 'if not defined OMNIX_START_HERMES set "OMNIX_START_HERMES=1"' in source
    assert 'start "Omnix Hermes" /min cmd /c "hermes gateway"' in source
    assert "Live Agent task requests will fall back to normal chat." in source
