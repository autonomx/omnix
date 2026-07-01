from __future__ import annotations

from app.assist_core.omnix_agent_metadata import omnix_agent_metadata_payload


def test_omnix_agent_metadata_flags() -> None:
    payload = omnix_agent_metadata_payload("x")

    assert payload["ok"] is True
    assert payload["mode"] == "agent_mode"
    assert payload["review_required"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False
