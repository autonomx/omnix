from __future__ import annotations

from app.assist_core.omnix_modes_metadata import omnix_modes_metadata_payload


def test_modes_metadata_count() -> None:
    payload = omnix_modes_metadata_payload()

    assert payload["ok"] is True
    assert payload["mode_count"] == 6
