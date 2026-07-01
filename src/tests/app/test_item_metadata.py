from __future__ import annotations

from app.assist_core.omnix_mode_item_metadata import omnix_mode_item_metadata_payload


def test_item_metadata_single() -> None:
    payload = omnix_mode_item_metadata_payload("normal_chat")

    assert payload["ok"] is True
    assert payload["single"] is True
