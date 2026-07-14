from __future__ import annotations

from pathlib import Path

import pytest

from app.rpg.narrative_engine.publisher_audit import audit_publisher_ownership
from app.rpg.narrative_engine.publisher_guard import (
    CANONICAL_PUBLISHER,
    LegacyNarrativePublisherError,
    publish_canonical_bundle,
    publisher_guard,
)


REPO_ROOT = Path(__file__).resolve().parents[4]


def _bundle() -> dict:
    return {
        "schema_version": "rpg_narrative_consumer_bundle_v1",
        "response_id": "response:publisher",
        "content_hash": "sha256:publisher",
        "visible_response": {"plain_text": "Canonical only."},
    }


def test_canonical_publication_records_zero_alternate_publishers() -> None:
    publisher_guard.reset_for_tests()
    try:
        published, telemetry = publish_canonical_bundle(_bundle())
        assert published["response_id"] == "response:publisher"
        assert telemetry.canonical_publish_count == 1
        assert telemetry.alternate_publish_count == 0
        assert telemetry.zero_alternate_publishers is True
        assert telemetry.last_publisher == CANONICAL_PUBLISHER
    finally:
        publisher_guard.reset_for_tests()


def test_alternate_publisher_is_rejected_before_visible_publication() -> None:
    publisher_guard.reset_for_tests()
    try:
        with pytest.raises(LegacyNarrativePublisherError):
            publish_canonical_bundle(_bundle(), publisher="legacy_world_scene_narrator")
        telemetry = publisher_guard.snapshot()
        assert telemetry.canonical_publish_count == 0
        assert telemetry.alternate_publish_count == 1
        assert telemetry.rejected_alternate_count == 1
        assert telemetry.zero_alternate_publishers is False
    finally:
        publisher_guard.reset_for_tests()


def test_production_source_has_one_guarded_publisher_owner() -> None:
    audit = audit_publisher_ownership(REPO_ROOT)
    assert audit.passed is True, audit.as_dict()
    assert all(audit.checks.values())
