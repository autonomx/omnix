from __future__ import annotations

import pytest

from app.rpg.worlds.generation_certified_publication import (
    _required_starter_certificate,
)
from app.rpg.worlds.generation_starter_bubble_publication import (
    StarterBubblePublicationError,
)


def _run() -> dict:
    return {
        "graph": {
            "metadata": {
                "starter_bubble_contract": {
                    "schema_version": "rpg_world_starter_bubble_contract_v1",
                    "required": True,
                    "domain_ids": [
                        "regions",
                        "places",
                        "actors",
                        "equipment_vehicles",
                    ],
                }
            }
        }
    }


def test_required_profile_certificate_cannot_be_missing_or_disabled() -> None:
    with pytest.raises(
        StarterBubblePublicationError,
        match="starter_bubble_certificate_required",
    ):
        _required_starter_certificate(_run(), {})

    with pytest.raises(
        StarterBubblePublicationError,
        match="starter_bubble_certificate_required",
    ):
        _required_starter_certificate(
            _run(),
            {
                "starter_bubble_release": {
                    "passed": True,
                    "materialization": {"contract_enabled": False},
                }
            },
        )


def test_required_profile_certificate_is_returned_when_enabled() -> None:
    certificate = {"contract_enabled": True, "content_hash": "sha256:test"}

    result = _required_starter_certificate(
        _run(),
        {
            "starter_bubble_release": {
                "passed": True,
                "materialization": certificate,
            }
        },
    )

    assert result == certificate


def test_legacy_graph_may_publish_without_release_six_contract() -> None:
    assert _required_starter_certificate({"graph": {"metadata": {}}}, {}) is None
