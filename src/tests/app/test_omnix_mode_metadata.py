from __future__ import annotations

from app.assist_core.omnix_mode_metadata import omnix_mode_metadata_payload


def test_omnix_mode_metadata_rpg() -> None:
    payload = omnix_mode_metadata_payload("rpg")

    assert payload["ok"] is True
    assert payload["read_only"] is True
    assert payload["executes"] is False
    assert payload["route"]["execution_owner"] == "rpg_sim"


def test_omnix_mode_metadata_all() -> None:
    payload = omnix_mode_metadata_payload()

    assert payload["ok"] is True
    assert len(payload["routes"]) == 6
