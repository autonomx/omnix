from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.assistant_memory.companion_context import (
    build_companion_context_packet,
    invalidate_companion_context,
)
from app.assistant_memory.lifecycle import resolve_snapshot_view
from app.assistant_memory.models import MemoryRecord, MemoryScopeContext
from app.assistant_memory.owner_repository import OwnerAwareInMemoryMemoryRepository
from app.assistant_memory.owner_service import OwnerAwareMemoryService
from app.assistant_memory.temporal_retrieval import (
    invalidate_temporal_retrieval,
    rank_temporal_records,
)
from app.assistant_memory.typed_memory import create_typed_memory, supersede_typed_memory
from app.chat.prompt_assembly import PromptMemoryItem


def _context() -> MemoryScopeContext:
    return MemoryScopeContext(
        profile_id="profile:default",
        workspace_id="workspace:local",
        project_id="project:companion",
        session_id="chat:completion",
        owner_type="character",
        owner_id="character:maya",
    )


def _session(snapshot_id: str | None = None, snapshot_revision: int | None = None):
    return SimpleNamespace(
        id="chat:completion",
        profile_id="profile:default",
        workspace_id="workspace:local",
        project_id="project:companion",
        interaction_mode="character",
        character_id="character:maya",
        memory_enabled=True,
        read_memory=True,
        write_memory=True,
        shared_memory_access="none",
        transcript_policy="persistent",
        memory_snapshot_id=snapshot_id,
        memory_snapshot_revision=snapshot_revision,
    )


def _prompt(record: MemoryRecord) -> PromptMemoryItem:
    return PromptMemoryItem(
        memory_id=record.id,
        content=record.content,
        scope=record.scope,
        category=record.category,
        revision=record.revision,
        source="character",
    )


def test_restart_multiworker_and_forget_propagate_everywhere() -> None:
    repository_key = "completion:restart-multiworker-forget"
    context = _context()
    service_a = OwnerAwareMemoryService(OwnerAwareInMemoryMemoryRepository(repository_key))
    service_a.repository.delete_owner(owner_type=context.owner_type, owner_id=context.owner_id)
    route = create_typed_memory(
        service_a,
        context,
        kind="routine",
        content="The user takes Route X to work",
        payload={
            "activity": "take_route_x",
            "days": ["MO", "TU", "WE", "TH", "FR"],
            "start_time": "07:00",
            "timezone": "America/Vancouver",
            "evidence_count": 4,
        },
        scope="global",
        provenance_id="message:route",
        contradiction_group="routine:commute",
    )
    snapshot = service_a.create_session_snapshot(context, token_budget=1_000)

    service_b = OwnerAwareMemoryService(OwnerAwareInMemoryMemoryRepository(repository_key))
    assert [item.id for item in service_b.list_active(context)] == [route.id]
    now = datetime(2026, 7, 20, 7, 5, tzinfo=ZoneInfo("America/Vancouver"))
    assert rank_temporal_records(
        service_b.list_active(context),
        "hello",
        now=now,
        timezone_name="America/Vancouver",
    )
    session = _session(snapshot.id, snapshot.revision)
    packet = build_companion_context_packet(
        session,
        SimpleNamespace(content="hello"),
        [_prompt(route)],
        now=now,
        timezone_name="America/Vancouver",
        locale="en-CA",
        privacy_policy="persistent:character-read-write",
    )
    assert [item.memory_id for item in packet.prompt_memory] == [route.id]

    assert service_b.forget_memory(
        context,
        route.id,
        expected_revision=route.revision,
    ) is True
    invalidate_companion_context(context.session_id)
    invalidate_temporal_retrieval(owner_type=context.owner_type, owner_id=context.owner_id)

    service_c = OwnerAwareMemoryService(OwnerAwareInMemoryMemoryRepository(repository_key))
    assert service_c.list_active(context) == []
    snapshot_view = resolve_snapshot_view(service_c, context, snapshot.id)
    assert snapshot_view is not None
    assert snapshot_view.active_count == 0
    assert rank_temporal_records(
        service_c.list_active(context),
        "hello",
        now=now,
        timezone_name="America/Vancouver",
    ) == ()
    empty_packet = build_companion_context_packet(
        session,
        SimpleNamespace(content="hello"),
        [],
        now=now,
        timezone_name="America/Vancouver",
        locale="en-CA",
        privacy_policy="persistent:character-read-write",
    )
    assert empty_packet.prompt_memory == []
    assert empty_packet.cache_hit is False
    assert any(
        event["event_type"] == "memory.forgotten"
        for event in service_c.repository.list_events(entity_id=route.id)
    )


def test_contradiction_and_temporary_exception_stop_old_routine_surface() -> None:
    repository_key = "completion:contradiction-exception"
    context = _context()
    service = OwnerAwareMemoryService(OwnerAwareInMemoryMemoryRepository(repository_key))
    service.repository.delete_owner(owner_type=context.owner_type, owner_id=context.owner_id)
    driving = create_typed_memory(
        service,
        context,
        kind="routine",
        content="The user drives Route X to work",
        payload={
            "activity": "drive_route_x",
            "days": ["MO", "TU", "WE", "TH", "FR"],
            "start_time": "07:00",
            "exceptions": ["2026-07-20"],
        },
        provenance_id="message:drive",
        contradiction_group="routine:commute",
    )
    zone = ZoneInfo("America/Vancouver")
    assert rank_temporal_records(
        [driving],
        "hello",
        now=datetime(2026, 7, 20, 7, 0, tzinfo=zone),
        timezone_name=zone.key,
    ) == ()
    assert rank_temporal_records(
        [driving],
        "hello",
        now=datetime(2026, 7, 21, 7, 0, tzinfo=zone),
        timezone_name=zone.key,
    )

    train = supersede_typed_memory(
        service,
        context,
        driving.id,
        kind="routine",
        content="The user now takes the train to work",
        payload={
            "activity": "train_to_work",
            "days": ["MO", "TU", "WE", "TH", "FR"],
            "start_time": "07:00",
        },
        provenance_id="message:train",
    )
    assert service.repository.get_record(driving.id).status == "superseded"
    assert [item.id for item in service.list_active(context)] == [train.id]
    selected = rank_temporal_records(
        service.list_active(context),
        "hello",
        now=datetime(2026, 7, 21, 7, 0, tzinfo=zone),
        timezone_name=zone.key,
    )
    assert [item.memory_id for item in selected] == [train.id]
