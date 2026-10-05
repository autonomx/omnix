"""Curated projection and the activation rule of the cutover command (WP-8.5)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.assistant_memory.v2 import MemorySpaceKey, ObservationProvenance, VisibilityScope
from app.assistant_memory.v2.contracts import Observation
from app.assistant_memory.v2.cutover import CutoverRefused, ready_receipts
from app.assistant_memory.v2.legacy_shadow import curated_projector

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


def _report(*statuses: str, unimported: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        unimported_v1_owner_count=unimported,
        spaces=[
            SimpleNamespace(status=status, readiness=SimpleNamespace(receipt_id=f"receipt:{index}"))
            for index, status in enumerate(statuses)
        ],
    )


def test_activation_takes_every_ready_receipt() -> None:
    assert ready_receipts(_report("ready", "ready"), v1_records=2) == ("receipt:0", "receipt:1")


def test_activation_with_nothing_to_migrate_takes_no_receipt() -> None:
    assert ready_receipts(_report(), v1_records=0) == ()


@pytest.mark.parametrize(("report", "v1_records", "message"), [
    (_report("ready", unimported=1), 1, "not imported"),
    (_report("ready", "v1_changed"), 2, "not ready"),
    (_report("ready", "shadow_failed"), 2, "not ready"),
    (_report(), 3, "nothing is imported"),
])
def test_activation_waits_for_a_complete_shadow_run(report, v1_records: int, message: str) -> None:
    with pytest.raises(CutoverRefused, match=message):
        ready_receipts(report, v1_records=v1_records)
