from __future__ import annotations

import pytest

from app.assistant_memory.models import MemoryScopeContext
from app.assistant_memory.owner_repository import OwnerAwareInMemoryMemoryRepository
from app.assistant_memory.owner_service import OwnerAwareMemoryService
from app.assistant_memory.typed_memory import (
    create_typed_memory,
    supersede_typed_memory,
    validate_typed_payload,
)


def _context() -> MemoryScopeContext:
    return MemoryScopeContext(
        profile_id="profile:default",
        workspace_id="workspace:local",
        project_id=None,
        session_id="chat:typed",
        owner_type="character",
        owner_id="character:maya",
    )


def test_routine_payload_is_validated_and_persisted() -> None:
    service = OwnerAwareMemoryService(OwnerAwareInMemoryMemoryRepository("typed:routine"))
    record = create_typed_memory(
        service,
        _context(),
        kind="routine",
        content="The user usually takes Route X at seven on weekdays.",
        payload={
            "activity": "commute_to_work",
            "days": ["MO", "TU", "WE", "TH", "FR"],
            "start_time": "06:50",
            "end_time": "07:20",
            "timezone": "America/Vancouver",
            "evidence_count": 4,
        },
        scope="global",
    )

    assert record.kind == "routine"
    assert record.category == "fact"
    assert record.structured_payload["activity"] == "commute_to_work"
    assert record.structured_payload["evidence_count"] == 4


def test_invalid_routine_time_and_day_are_rejected() -> None:
    with pytest.raises(ValueError):
        validate_typed_payload(
            "routine",
            {"activity": "commute", "days": ["XX"], "start_time": "25:10"},
        )


def test_supersession_is_deterministic_and_auditable() -> None:
    service = OwnerAwareMemoryService(OwnerAwareInMemoryMemoryRepository("typed:replace"))
    original = create_typed_memory(
        service,
        _context(),
        kind="routine",
        content="The user drives on Route X.",
        payload={"activity": "commute", "days": ["MO"], "evidence_count": 2},
    )
    replacement = supersede_typed_memory(
        service,
        _context(),
        original.id,
        kind="routine",
        content="The user now takes the train.",
        payload={"activity": "commute", "days": ["MO"], "evidence_count": 1},
    )

    archived = service.repository.get_record(original.id)
    assert archived is not None
    assert archived.status == "superseded"
    assert replacement.supersedes_memory_id == original.id
    assert replacement.contradiction_group == f"memory-claim:{original.id}"
