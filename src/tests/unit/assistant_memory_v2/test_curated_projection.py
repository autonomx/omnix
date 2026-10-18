"""Curated projection and the activation rule of the cutover command (WP-8.5)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.platform.assistant_memory.v2 import MemorySpaceKey, ObservationProvenance, VisibilityScope
from app.platform.assistant_memory.v2.contracts import Observation

from app.platform.assistant_memory.v2.curated_projection import curated_projector

SPACE = MemorySpaceKey(principal_id="workspace:local", owner_type="character", owner_id="sofia")
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


def _observation(event_type: str, record: dict, *, sequence: int = 1) -> Observation:
    key = "legacy_record" if event_type == "imported_legacy_memory" else "memory_record"
    return Observation(
        observation_id=f"obs:{sequence}",
        space=SPACE,
        authority_sequence=sequence,
        idempotency_key=f"key:{sequence}",
        visibility_scope=VisibilityScope(kind="global", scope_id="profile:alice"),
        event_type=event_type,
        occurred_at=NOW,
        provenance=ObservationProvenance(
            source_type="migration" if event_type == "imported_legacy_memory" else "user",
            source_id="memory:1",
            trust_level="user_explicit",
        ),
        recorded_at=NOW,
        payload={key: record},
        content_digest="digest00",
    )


def _record(**changes) -> dict:
    record = {
        "id": "memory:1", "content": "Skyrim is my favorite game", "kind": "preference",
        "status": "active", "sensitivity": "normal", "trust_level": "user_approved",
        "revision": 1, "confidence": 1.0,
    }
    record.update(changes)
    return record


def test_an_eligible_curated_record_becomes_its_own_text() -> None:
    (assertion,) = curated_projector((_observation("curated_memory", _record()),))
    assert assertion.assertion_id.startswith("curated:")
    assert assertion.object.literal == "Skyrim is my favorite game"
    assert assertion.assertion_type == "seeded"
    assert assertion.derivation_version == "memory-v2-curated@1"


@pytest.mark.parametrize("change", [
    {"sensitivity": "secret"},
    {"trust_level": "unverified_agent"},
    {"status": "archived"},
    {"status": "superseded"},
])
def test_records_v1_keeps_out_of_prompts_are_not_derived(change: dict) -> None:
    assert curated_projector((_observation("curated_memory", _record(**change)),)) == ()
    assert curated_projector((_observation("imported_legacy_memory", _record(**change)),)) == ()


def test_a_curated_record_keeps_one_assertion_across_revisions() -> None:
    first = curated_projector((_observation("curated_memory", _record()),))
    edited = curated_projector((_observation("curated_memory", _record(revision=2, content="Morrowind"), sequence=2),))
    assert first[0].assertion_id == edited[0].assertion_id



