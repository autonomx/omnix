from __future__ import annotations

from app.assist_core.omnix_route_decision import omnix_route_decision_payload


def test_omnix_route_decision_defaults_to_rpg() -> None:
    payload = omnix_route_decision_payload()

    assert payload["ok"] is True
    assert payload["mode"] == "rpg"
    assert payload["role"] == "suggest"
    assert payload["owner"] == "rpg_sim"
    assert payload["review_required"] is False
    assert "suggest" in payload["capabilities"]


def test_omnix_route_decision_reports_unknown_mode() -> None:
    assert omnix_route_decision_payload("unknown") == {
        "ok": False,
        "error": "unknown_mode",
        "mode": "unknown",
        "source": "omnix_route_decision",
    }
