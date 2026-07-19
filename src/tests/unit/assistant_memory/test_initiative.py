from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.assistant_memory.initiative import (
    TrustedCapabilityManifest,
    initiative_prompt_directive,
    plan_companion_initiative,
    record_initiative_surface,
    reset_initiative_surface_history,
)
from app.assistant_memory.models import MemoryRecord, MemoryScopeContext
from app.assistant_memory.temporal_retrieval import (
    TemporalRetrievalResult,
    rank_temporal_records,
)
from app.characters.live_conversation_profile import LiveConversationProfile


def _record(*, score_kind: str = "routine", content: str = "The user takes Route X to work.") -> MemoryRecord:
    return MemoryRecord(
        id="memory:route-x",
        owner_type="character",
        owner_id="character:maya",
        scope="global",
        scope_id="profile:default",
        category="fact",
        kind=score_kind,
        structured_payload={
            "activity": "commute_to_work",
            "days": ["MO", "TU", "WE", "TH", "FR"],
            "start_time": "07:00",
            "timezone": "America/Vancouver",
            "evidence_count": 4,
        },
        source="user_saved",
        content=content,
        normalized_content=content.casefold(),
        confidence=0.9,
        pinned=False,
        trust_level="user_approved",
        sensitivity="normal",
        provenance_type="user_message",
        provenance_id="message:1",
        status="active",
        revision=1,
        created_at="2026-07-01T00:00:00+00:00",
        updated_at="2026-07-01T00:00:00+00:00",
    )


def _context() -> MemoryScopeContext:
    return MemoryScopeContext(
        profile_id="profile:default",
        workspace_id="workspace:local",
        project_id=None,
        session_id="chat:initiative",
        owner_type="character",
        owner_id="character:maya",
    )


def _result(now: datetime) -> TemporalRetrievalResult:
    selected = rank_temporal_records(
        [_record()],
        "hello",
        now=now,
        timezone_name="America/Vancouver",
    )
    return TemporalRetrievalResult(
        items=selected,
        candidate_count=1,
        selected_count=len(selected),
        preload_cache_hit=True,
        preload_timed_out=False,
        preload_ms=0.2,
        rank_ms=0.1,
        deadline_ms=50.0,
        timezone="America/Vancouver",
    )


def test_gentle_route_routine_can_surface_and_request_traffic() -> None:
    reset_initiative_surface_history()
    now = datetime(2026, 7, 20, 7, 5, tzinfo=ZoneInfo("America/Vancouver"))
    decision = plan_companion_initiative(
        _result(now),
        _context(),
        LiveConversationProfile(initiative_mode="gentle"),
        "hello",
        privacy_mode=False,
        capabilities=TrustedCapabilityManifest(available_tools=frozenset({"traffic"})),
        now=now,
    )

    assert decision.action == "surface_with_tool"
    assert decision.requested_tool == "traffic"
    assert decision.tool_available is True
    assert decision.proactive is True
    directive = initiative_prompt_directive(decision, _result(now))
    assert directive is not None
    assert "do not invent" in directive.casefold()


def test_tool_absence_produces_honest_fallback() -> None:
    reset_initiative_surface_history()
    now = datetime(2026, 7, 20, 7, 5, tzinfo=ZoneInfo("America/Vancouver"))
    decision = plan_companion_initiative(
        _result(now),
        _context(),
        LiveConversationProfile(initiative_mode="active"),
        "hello",
        privacy_mode=False,
        capabilities=TrustedCapabilityManifest(),
        now=now,
    )

    assert decision.action == "surface_without_tool"
    assert decision.reason == "tool_unavailable_fallback"
    directive = initiative_prompt_directive(decision, _result(now))
    assert directive is not None
    assert "unavailable" in directive.casefold()


def test_initiative_off_only_allows_directly_relevant_context() -> None:
    reset_initiative_surface_history()
    now = datetime(2026, 7, 20, 7, 5, tzinfo=ZoneInfo("America/Vancouver"))
    result = _result(now)

    greeting = plan_companion_initiative(
        result,
        _context(),
        LiveConversationProfile(initiative_mode="off"),
        "hello",
        privacy_mode=False,
        now=now,
    )
    direct = plan_companion_initiative(
        result,
        _context(),
        LiveConversationProfile(initiative_mode="off"),
        "Is Route X busy?",
        privacy_mode=False,
        now=now,
    )

    assert greeting.action == "suppress"
    assert direct.action == "context_only"
    assert direct.proactive is False


def test_private_session_suppresses_memory_initiative_and_tools() -> None:
    reset_initiative_surface_history()
    now = datetime(2026, 7, 20, 7, 5, tzinfo=ZoneInfo("America/Vancouver"))
    decision = plan_companion_initiative(
        _result(now),
        _context(),
        LiveConversationProfile(initiative_mode="active"),
        "hello",
        privacy_mode=True,
        capabilities=TrustedCapabilityManifest(available_tools=frozenset({"traffic"})),
        now=now,
    )

    assert decision.action == "suppress"
    assert decision.reason == "private_session"
    assert decision.requested_tool is None


def test_repetition_cooldown_prevents_repeated_morning_prompt() -> None:
    reset_initiative_surface_history()
    zone = ZoneInfo("America/Vancouver")
    first_morning = datetime(2026, 7, 20, 7, 5, tzinfo=zone)
    record_initiative_surface(_context(), "memory:route-x", surfaced_at=first_morning)

    too_soon = plan_companion_initiative(
        _result(first_morning + timedelta(hours=24)),
        _context(),
        LiveConversationProfile(initiative_mode="gentle"),
        "hello",
        privacy_mode=False,
        capabilities=TrustedCapabilityManifest(available_tools=frozenset({"traffic"})),
        now=first_morning + timedelta(hours=24),
    )
    later = plan_companion_initiative(
        _result(first_morning + timedelta(hours=48)),
        _context(),
        LiveConversationProfile(initiative_mode="gentle"),
        "hello",
        privacy_mode=False,
        capabilities=TrustedCapabilityManifest(available_tools=frozenset({"traffic"})),
        now=first_morning + timedelta(hours=48),
    )

    assert too_soon.reason == "repetition_cooldown"
    assert later.proactive is True
