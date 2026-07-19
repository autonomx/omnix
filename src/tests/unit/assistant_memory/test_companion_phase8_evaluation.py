from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.assistant_memory.initiative import (
    TrustedCapabilityManifest,
    plan_companion_initiative,
    reset_initiative_surface_history,
)
from app.assistant_memory.models import MemoryRecord, MemoryScopeContext
from app.assistant_memory.observability import (
    companion_metrics_snapshot,
    record_companion_diagnostics,
    reset_companion_metrics,
)
from app.assistant_memory.owner_repository import OwnerAwareInMemoryMemoryRepository
from app.assistant_memory.owner_service import OwnerAwareMemoryService
from app.assistant_memory.paralinguistic_state import (
    durable_affect_candidate_allowed,
    observe_paralinguistic_turn,
)
from app.assistant_memory.rollout import companion_rollout_policy
from app.assistant_memory.settings import (
    AssistantMemoryRuntimeSettings,
    AssistantMemorySettingsStore,
    AssistantMemorySettingsUpdate,
)
from app.assistant_memory.settings_routes import register_memory_settings_routes
from app.assistant_memory.structured_consolidation import consolidate_structured_proposal
from app.assistant_memory.structured_extraction import extract_structured_memory_proposals
from app.assistant_memory.temporal_retrieval import (
    TemporalRetrievalResult,
    rank_temporal_records,
)
from app.assistant_memory.typed_memory import supersede_typed_memory
from app.characters.live_conversation_profile import LiveConversationProfile


def _context(owner_id: str = "character:maya") -> MemoryScopeContext:
    return MemoryScopeContext(
        profile_id="profile:default",
        workspace_id="workspace:local",
        project_id=None,
        session_id="chat:phase8",
        owner_type="character",
        owner_id=owner_id,
    )


def _service(name: str = "phase8") -> OwnerAwareMemoryService:
    return OwnerAwareMemoryService(OwnerAwareInMemoryMemoryRepository(name))


def _temporal_result(records: list[MemoryRecord], query: str, now: datetime) -> TemporalRetrievalResult:
    selected = rank_temporal_records(
        records,
        query,
        now=now,
        timezone_name="America/Vancouver",
    )
    return TemporalRetrievalResult(
        items=selected,
        candidate_count=len(records),
        selected_count=len(selected),
        preload_cache_hit=True,
        preload_timed_out=False,
        preload_ms=0.2,
        rank_ms=0.1,
        deadline_ms=50.0,
        timezone="America/Vancouver",
    )


def test_rollout_is_reversible_and_master_disable_preserves_authority() -> None:
    active = companion_rollout_policy(
        AssistantMemoryRuntimeSettings(
            companion_rollout_stage="paralinguistic_pilot",
            automatic_direct_assertion_memory=True,
        )
    )
    shadow = companion_rollout_policy(
        AssistantMemoryRuntimeSettings(companion_rollout_stage="shadow")
    )
    disabled = companion_rollout_policy(
        AssistantMemoryRuntimeSettings(
            companion_master_enabled=False,
            companion_rollout_stage="paralinguistic_pilot",
        )
    )

    assert active.memory_read_enabled is True
    assert active.automatic_direct_assertions_enabled is True
    assert active.proactive_memory_enabled is True
    assert active.paralinguistic_signals_enabled is True
    assert shadow.shadow_metrics_enabled is True
    assert shadow.memory_read_enabled is False
    assert disabled.authority_enabled is True
    assert disabled.memory_read_enabled is False
    assert disabled.proactive_memory_enabled is False


def test_controls_persist_independently_and_environment_can_lock_stage(tmp_path, monkeypatch) -> None:
    path = tmp_path / "memory-settings.json"
    store = AssistantMemorySettingsStore(path)
    status = store.update(
        AssistantMemorySettingsUpdate(
            automatic_direct_assertion_memory=True,
            proactive_memory_enabled=False,
            paralinguistic_signals_enabled=False,
            transcript_retention_enabled=False,
            companion_rollout_stage="automatic_assertions",
        )
    )

    assert status.settings.automatic_direct_assertion_memory is True
    assert status.settings.proactive_memory_enabled is False
    assert status.settings.paralinguistic_signals_enabled is False
    assert status.settings.transcript_retention_enabled is False
    monkeypatch.setenv("OMNIX_COMPANION_ROLLOUT_STAGE", "shadow")
    effective = store.load_effective()
    assert effective.settings.companion_rollout_stage == "shadow"
    assert "companion_rollout_stage" in effective.environment_overrides


def test_commute_lifecycle_activation_tool_supersession_and_owner_isolation() -> None:
    reset_initiative_surface_history()
    service = _service("phase8:lifecycle")
    context = _context()
    proposals, skipped = extract_structured_memory_proposals(
        "I usually take Route X around 7am on weekdays",
        source_message_id="message:route",
    )
    assert skipped == []
    routine = next(item for item in proposals if item.kind == "routine")
    assert routine.content == "The user usually take Route X"
    assert routine.payload["activity"] == "take_route_x"
    assert routine.payload["start_time"] == "07:00"
    action, saved = consolidate_structured_proposal(
        service,
        context,
        routine,
        source_session_id=context.session_id,
        source_message_id="message:route",
        auto_save_direct_assertions=True,
    )
    assert action == "saved"
    for observation in range(2, 5):
        action, saved = consolidate_structured_proposal(
            service,
            context,
            routine,
            source_session_id=context.session_id,
            source_message_id=f"message:route:{observation}",
            auto_save_direct_assertions=True,
        )
        assert action == "duplicate_merged"
    assert saved.structured_payload["evidence_count"] == 4

    now = datetime(2026, 7, 20, 7, 5, tzinfo=ZoneInfo("America/Vancouver"))
    result = _temporal_result(service.list_active(context), "hello", now)
    assert result.items
    selected = result.items[0]
    assert selected.score >= 850
    assert "routine_start_window" in selected.reasons
    decision = plan_companion_initiative(
        result,
        context,
        LiveConversationProfile(initiative_mode="gentle"),
        "hello",
        privacy_mode=False,
        capabilities=TrustedCapabilityManifest(available_tools=frozenset({"traffic"})),
        now=now,
    )
    assert decision.action == "surface_with_tool", decision.model_dump(mode="json")
    assert decision.reason == "tool_enrichment_allowed"
    assert decision.activation_score == selected.score
    assert decision.requested_tool == "traffic"

    replacement = supersede_typed_memory(
        service,
        context,
        saved.id,
        kind="routine",
        content="The user now takes the train to work",
        payload={
            "activity": "train_to_work",
            "days": ["MO", "TU", "WE", "TH", "FR"],
            "start_time": "07:00",
            "evidence_count": 1,
        },
        provenance_id="message:train",
    )
    assert replacement.supersedes_memory_id == saved.id
    assert service.repository.get_record(saved.id).status == "superseded"
    assert [item.id for item in service.list_active(context)] == [replacement.id]
    assert service.list_active(_context("character:other")) == []


def test_private_paralinguistic_signal_never_becomes_durable_affect_memory() -> None:
    state = observe_paralinguistic_turn(
        "chat:private-phase8",
        "[sighs] um... maybe",
        metadata={"pause_ms": 1_200, "raw_audio": b"discarded"},
        private_mode=True,
    )
    assert state.private_mode is True
    assert state.signals
    assert durable_affect_candidate_allowed(state) is False
    serialized = state.model_dump(mode="json")
    assert "raw_audio" not in serialized
    assert "transcript" not in serialized


def test_observability_is_content_free_and_metrics_route_is_hidden() -> None:
    reset_companion_metrics()
    secret = "private Route X transcript"
    record_companion_diagnostics(
        {
            "companion_context": {
                "candidate_count": 10,
                "selected_count": 3,
                "build_ms": 4.5,
                "cache_hit": True,
                "content": secret,
            },
            "initiative": {
                "action": "surface_with_tool",
                "reason": "tool_enrichment_allowed",
                "proactive": True,
                "memory_content": secret,
            },
            "paralinguistic_state": {
                "signal_count": 2,
                "private_mode": True,
                "transcript": secret,
            },
        }
    )
    snapshot = companion_metrics_snapshot()
    payload = snapshot.model_dump(mode="json")
    assert snapshot.turns == 1
    assert snapshot.totals["companion_context.selected_count"] == 3
    assert secret not in str(payload)
    assert payload["diagnostics_policy"] == "content_free"

    app = FastAPI()
    register_memory_settings_routes(app)
    client = TestClient(app)
    response = client.get("/api/assistant/memory/metrics")
    assert response.status_code == 200
    assert response.json()["turns"] == 1
    assert "/api/assistant/memory/metrics" not in client.get("/openapi.json").json()["paths"]


def test_high_volume_temporal_ranking_stays_bounded() -> None:
    records: list[MemoryRecord] = []
    for index in range(1_000):
        records.append(
            MemoryRecord(
                id=f"memory:{index}",
                owner_type="character",
                owner_id="character:maya",
                scope="global",
                scope_id="profile:default",
                category="fact",
                kind="routine" if index == 999 else "semantic_fact",
                structured_payload=(
                    {
                        "activity": "commute_to_work",
                        "days": ["MO", "TU", "WE", "TH", "FR"],
                        "start_time": "07:00",
                        "evidence_count": 4,
                    }
                    if index == 999
                    else {}
                ),
                source="user_saved",
                content=(
                    "The user takes Route X to work"
                    if index == 999
                    else f"Unrelated durable fact {index}"
                ),
                normalized_content=f"fact {index}",
                confidence=0.9,
                pinned=False,
                trust_level="user_approved",
                sensitivity="normal",
                provenance_type="user_message",
                provenance_id=f"message:{index}",
                status="active",
                revision=1,
                created_at="2026-07-01T00:00:00+00:00",
                updated_at="2026-07-01T00:00:00+00:00",
            )
        )
    now = datetime(2026, 7, 20, 7, 5, tzinfo=ZoneInfo("America/Vancouver"))
    started = time.perf_counter()
    selected = rank_temporal_records(
        records,
        "hello",
        now=now,
        timezone_name="America/Vancouver",
        limit=12,
    )
    elapsed_ms = (time.perf_counter() - started) * 1_000
    assert selected[0].memory_id == "memory:999"
    assert len(selected) <= 12
    assert elapsed_ms < 250
