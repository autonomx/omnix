from __future__ import annotations

import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.assistant_memory.companion_context import (
    build_companion_context_packet,
    invalidate_companion_context,
)
from app.chat.prompt_assembly import PromptMemoryItem


def _session(**updates) -> SimpleNamespace:
    values = {
        "id": "chat:companion",
        "profile_id": "profile:default",
        "workspace_id": "workspace:local",
        "project_id": "project:one",
        "interaction_mode": "character",
        "character_id": "character:maya",
        "memory_enabled": True,
        "read_memory": True,
        "write_memory": False,
        "shared_memory_access": "read",
        "transcript_policy": "persistent",
        "memory_snapshot_id": "snapshot:1",
        "memory_snapshot_revision": 3,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def _item(
    index: int,
    category: str,
    content: str,
    *,
    scope: str = "global",
) -> PromptMemoryItem:
    return PromptMemoryItem(
        memory_id=f"memory:{index}",
        content=content,
        scope=scope,
        category=category,
        revision=1,
        source="character",
    )


def test_packet_is_bounded_sectioned_and_query_relevant() -> None:
    invalidate_companion_context()
    memories = [
        _item(1, "preference", "The user prefers concise morning greetings."),
        _item(2, "relationship", "James is the user's close colleague."),
        _item(3, "project", "The user is evaluating Burnaby condos."),
        _item(4, "fact", "The weekday commute uses Route X around seven."),
    ]
    message = SimpleNamespace(content="How is Route X this morning?")

    packet = build_companion_context_packet(
        _session(),
        message,
        memories,
        token_budget=1_000,
    )

    assert packet.owner_type == "character"
    assert packet.owner_id == "character:maya"
    assert packet.selected_count == 4
    assert packet.token_estimate <= 1_000
    assert packet.sections["communication_preferences"][0].memory_id == "memory:1"
    assert packet.sections["relationship_context"][0].memory_id == "memory:2"
    assert packet.sections["active_goals"][0].memory_id == "memory:3"
    route = packet.sections["stable_profile"][0]
    assert route.memory_id == "memory:4"
    assert route.selection_reason == "current_turn_term_overlap"
    assert packet.prompt_memory[0].memory_id == "memory:1"


def test_packet_cache_is_content_safe_and_fast() -> None:
    invalidate_companion_context()
    memories = [
        _item(
            index,
            "fact" if index % 2 else "preference",
            f"Stable companion detail number {index} for the user.",
            scope="workspace",
        )
        for index in range(200)
    ]
    message = SimpleNamespace(content="hello")
    now = datetime(2026, 7, 20, 7, 5, tzinfo=ZoneInfo("America/Vancouver"))

    first = build_companion_context_packet(
        _session(),
        message,
        memories,
        token_budget=1_000,
        now=now,
        timezone_name="America/Vancouver",
    )
    started = time.perf_counter()
    second = build_companion_context_packet(
        _session(),
        message,
        memories,
        token_budget=1_000,
        now=now,
        timezone_name="America/Vancouver",
    )
    elapsed_ms = (time.perf_counter() - started) * 1_000

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.token_estimate <= 1_000
    assert elapsed_ms < 25
    diagnostics = second.content_free_diagnostics()
    assert "content" not in repr(diagnostics).lower()
    assert diagnostics["selected_count"] == second.selected_count
    assert diagnostics["cache_dimension_version"] == 2


def test_packet_cache_key_covers_scope_privacy_locale_timezone_and_time_bucket() -> None:
    invalidate_companion_context()
    memories = [_item(1, "fact", "The user takes Route X.", scope="workspace")]
    message = SimpleNamespace(content="hello")
    now = datetime(2026, 7, 20, 7, 5, tzinfo=ZoneInfo("America/Vancouver"))
    common = {
        "token_budget": 1_000,
        "privacy_policy": "persistent:read-only",
        "locale": "en-CA",
        "timezone_name": "America/Vancouver",
        "now": now,
    }

    first = build_companion_context_packet(_session(), message, memories, **common)
    repeated = build_companion_context_packet(_session(), message, memories, **common)
    different_workspace = build_companion_context_packet(
        _session(workspace_id="workspace:other"), message, memories, **common
    )
    different_project = build_companion_context_packet(
        _session(project_id="project:other"), message, memories, **common
    )
    different_privacy = build_companion_context_packet(
        _session(), message, memories, **{**common, "privacy_policy": "temporary:no-write"}
    )
    different_locale = build_companion_context_packet(
        _session(), message, memories, **{**common, "locale": "fr-CA"}
    )
    different_timezone = build_companion_context_packet(
        _session(), message, memories, **{**common, "timezone_name": "America/Toronto"}
    )
    different_bucket = build_companion_context_packet(
        _session(), message, memories, **{**common, "now": now + timedelta(minutes=16)}
    )

    assert first.cache_hit is False
    assert repeated.cache_hit is True
    assert different_workspace.cache_hit is False
    assert different_project.cache_hit is False
    assert different_privacy.cache_hit is False
    assert different_locale.cache_hit is False
    assert different_timezone.cache_hit is False
    assert different_bucket.cache_hit is False


def test_packet_truncates_deterministically() -> None:
    invalidate_companion_context()
    memories = [
        _item(1, "instruction", "Always speak gently and naturally."),
        _item(2, "preference", "The user prefers a short answer."),
        _item(3, "fact", "The user commutes by train."),
    ]

    first = build_companion_context_packet(
        _session(),
        SimpleNamespace(content="hello"),
        memories,
        token_budget=20,
    )
    second = build_companion_context_packet(
        _session(),
        SimpleNamespace(content="hello"),
        memories,
        token_budget=20,
    )

    assert first.truncated is True
    assert [item.memory_id for item in first.prompt_memory] == [
        item.memory_id for item in second.prompt_memory
    ]
