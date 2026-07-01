from __future__ import annotations

from app.assist_core.omnix_mode_item_metadata import omnix_mode_item_metadata_payload
from app.assist_core.omnix_mode_metadata import omnix_mode_metadata_payload


def test_mode_metadata_unknown_mode() -> None:
    payload = omnix_mode_metadata_payload("missing")

    assert payload["ok"] is False
    assert payload["error"] == "unknown_mode"
    assert payload["read_only"] is True
    assert payload["executes"] is False


def test_mode_item_metadata_unknown_mode() -> None:
    payload = omnix_mode_item_metadata_payload("missing")

    assert payload["ok"] is False
    assert payload["error"] == "unknown_mode"
