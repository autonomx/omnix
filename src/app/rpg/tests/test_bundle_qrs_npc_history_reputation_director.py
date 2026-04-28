"""Bundle QRS: NPC History, Reputation, and Conversation Director tests."""
from __future__ import annotations

from typing import Any, Dict

import pytest

from app.rpg.world.conversation_director import (
    ensure_conversation_director_state,
    present_npcs_for_location,
    select_conversation_intent,
)
from app.rpg.world.conversation_settings import normalize_conversation_settings
from app.rpg.world.npc_history_state import (
    MAX_HISTORY_ENTRIES_PER_NPC,
    add_npc_history_entry,
    ensure_npc_history_state,
    prune_npc_history_state,
    recent_npc_history,
)
from app.rpg.world.npc_reputation_state import (
    ensure_npc_reputation_state,
    get_npc_reputation,
    response_style_from_reputation,
    update_npc_reputation,
)

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_sim(*, quests=None) -> Dict[str, Any]:
    sim: Dict[str, Any] = {
        "location_state": {"current_location_id": "loc_tavern"},
        "conversation_settings": {},
    }
    if quests:
        sim["quest_state"] = {"quests": quests}
    return sim


# ── Bundle Q: NPC History ──────────────────────────────────────────────────


def test_npc_history_is_bounded_and_prunes_expired():
    sim: Dict[str, Any] = {}
    # Add entries at tick 1 with short TTL
    for i in range(25):
        add_npc_history_entry(
            sim,
            npc_id="npc:Bran",
            kind="player_conversation_reply",
            summary=f"Entry {i}",
            tick=1,
            ttl_ticks=10,
        )
    state = ensure_npc_history_state(sim)
    entries = state["by_npc"]["npc:Bran"]["entries"]
    assert len(entries) <= MAX_HISTORY_ENTRIES_PER_NPC, "Entries must be bounded to MAX_HISTORY_ENTRIES_PER_NPC"

    # Prune at tick > expires_tick (1 + 10 = 11)
    result = prune_npc_history_state(sim, current_tick=15)
    assert isinstance(result.get("expired_history_ids"), list)
    state_after = ensure_npc_history_state(sim)
    remaining = state_after["by_npc"]["npc:Bran"]["entries"]
    for entry in remaining:
        assert entry.get("expires_tick", 999) > 15, "Expired entries must be pruned"


def test_npc_history_deduplicates_same_tick_and_kind():
    sim: Dict[str, Any] = {}
    for _ in range(5):
        add_npc_history_entry(
            sim,
            npc_id="npc:Bran",
            kind="player_conversation_reply",
            summary="Duplicate summary",
            tick=100,
        )
    state = ensure_npc_history_state(sim)
    entries = state["by_npc"]["npc:Bran"]["entries"]
    # Same summary + kind + tick should not produce 5 duplicate entries
    matching = [e for e in entries if e.get("summary") == "Duplicate summary"]
    assert len(matching) == 1, f"Expected 1 deduplicated entry, got {len(matching)}"


def test_npc_history_invalid_npc_id_rejected():
    sim: Dict[str, Any] = {}
    result = add_npc_history_entry(
        sim,
        npc_id="notanpc",
        kind="player_conversation_reply",
        summary="This should not be added.",
        tick=1,
    )
    assert result.get("created") is False


def test_recent_npc_history_returns_sorted_by_tick():
    sim: Dict[str, Any] = {}
    for tick in [5, 3, 7, 1]:
        add_npc_history_entry(
            sim,
            npc_id="npc:Mira",
            kind="player_conversation_reply",
            summary=f"At tick {tick}",
            tick=tick,
        )
    recent = recent_npc_history(sim, npc_id="npc:Mira", limit=10)
    ticks = [e.get("tick") for e in recent]
    assert ticks == sorted(ticks, reverse=True), "recent_npc_history must return entries newest-first"


# ── Bundle R: NPC Reputation ──────────────────────────────────────────────


def test_npc_reputation_updates_and_clamps():
    sim: Dict[str, Any] = {}
    # Start at 0 for all axes
    rep = get_npc_reputation(sim, npc_id="npc:Bran")
    assert rep["familiarity"] == 0
    assert rep["trust"] == 0

    # Update by +3
    update_npc_reputation(sim, npc_id="npc:Bran", tick=10, familiarity_delta=3, trust_delta=2)
    rep = get_npc_reputation(sim, npc_id="npc:Bran")
    assert rep["familiarity"] == 3
    assert rep["trust"] == 2

    # Clamp at REPUTATION_MAX (5)
    update_npc_reputation(sim, npc_id="npc:Bran", tick=11, familiarity_delta=10)
    rep = get_npc_reputation(sim, npc_id="npc:Bran")
    assert rep["familiarity"] == 5, "Reputation must be clamped at REPUTATION_MAX"

    # Clamp at REPUTATION_MIN (-5)
    update_npc_reputation(sim, npc_id="npc:Bran", tick=12, trust_delta=-20)
    rep = get_npc_reputation(sim, npc_id="npc:Bran")
    assert rep["trust"] == -5, "Reputation must be clamped at REPUTATION_MIN"


def test_npc_reputation_invalid_npc_id_rejected():
    sim: Dict[str, Any] = {}
    result = update_npc_reputation(sim, npc_id="notannpc", tick=1, familiarity_delta=1)
    assert result.get("updated") is False


def test_reputation_response_style_changes():
    base: Dict[str, Any] = {
        "npc_id": "npc:Bran",
        "familiarity": 0,
        "trust": 0,
        "annoyance": 0,
        "fear": 0,
        "respect": 0,
    }

    assert response_style_from_reputation(base) == "guarded"

    assert response_style_from_reputation({**base, "trust": 1}) == "friendly"
    assert response_style_from_reputation({**base, "trust": 2, "respect": 1}) == "helpful"
    assert response_style_from_reputation({**base, "annoyance": 3}) == "annoyed"
    assert response_style_from_reputation({**base, "fear": 3}) == "evasive"


# ── Bundle S: Conversation Director ────────────────────────────────────────


def test_conversation_director_selects_backed_topic():
    sim = _make_sim(
        quests=[
            {
                "quest_id": "quest:old_mill_bandits",
                "title": "Trouble near the Old Mill",
                "summary": "Armed figures near the old mill road.",
                "status": "active",
                "location_id": "loc_tavern",
            }
        ]
    )
    settings = normalize_conversation_settings(
        {
            "conversation_director_enabled": True,
            "conversation_director_cooldown_ticks": 4,
            "allow_quest_discussion": True,
        }
    )
    intent = select_conversation_intent(sim, settings=settings, tick=10)
    assert intent.get("selected") is True
    assert intent.get("speaker_id", "").startswith("npc:")
    assert intent.get("listener_id", "").startswith("npc:")
    assert intent.get("topic_id") != ""
    assert intent.get("source") == "deterministic_conversation_director"


def test_conversation_director_respects_cooldown():
    sim = _make_sim(
        quests=[
            {
                "quest_id": "quest:old_mill_bandits",
                "title": "Trouble near the Old Mill",
                "summary": "Armed figures near the old mill road.",
                "status": "active",
                "location_id": "loc_tavern",
            }
        ]
    )
    settings = normalize_conversation_settings(
        {
            "conversation_director_enabled": True,
            "conversation_director_cooldown_ticks": 10,
            "allow_quest_discussion": True,
        }
    )
    # First call at tick=10 should select
    intent1 = select_conversation_intent(sim, settings=settings, tick=10)
    assert intent1.get("selected") is True

    # Second call at tick=12 (within cooldown) should not reselect the same pair+topic
    intent2 = select_conversation_intent(sim, settings=settings, tick=12)
    if intent2.get("selected"):
        # If selected, it must be a different combination (different cooldown key)
        assert not (
            intent2.get("speaker_id") == intent1.get("speaker_id")
            and intent2.get("listener_id") == intent1.get("listener_id")
            and intent2.get("topic_id") == intent1.get("topic_id")
        ), "Director should not repeat a cooled-down speaker/listener/topic combination"


def test_director_does_not_mutate_forbidden_state():
    sim = _make_sim(
        quests=[
            {
                "quest_id": "quest:old_mill_bandits",
                "title": "Trouble near the Old Mill",
                "summary": "Armed figures near the old mill road.",
                "status": "active",
                "location_id": "loc_tavern",
            }
        ]
    )
    # Record state keys that must not be created by the director
    forbidden_keys = {
        "inventory_state",
        "currency_state",
        "journal_state",
        "combat_state",
    }
    initial_quest_state = sim.get("quest_state")

    settings = normalize_conversation_settings(
        {
            "conversation_director_enabled": True,
            "allow_quest_discussion": True,
        }
    )
    select_conversation_intent(sim, settings=settings, tick=1)

    for key in forbidden_keys:
        assert key not in sim, f"Director must not create {key}"


def test_director_tavern_fallback_does_not_include_guard_captain():
    state = {
        "location_state": {"current_location_id": "loc_tavern"},
    }

    present = present_npcs_for_location(state, location_id="loc_tavern")

    assert "npc:Bran" in present
    assert "npc:Mira" in present
    assert "npc:GuardCaptain" not in present


def test_director_uses_explicit_present_guard_captain_when_listed():
    state = {
        "location_state": {"current_location_id": "loc_tavern"},
        "present_npc_state": {
            "loc_tavern": ["npc:Bran", "npc:Mira", "npc:GuardCaptain"]
        },
    }

    present = present_npcs_for_location(state, location_id="loc_tavern")

    assert "npc:GuardCaptain" in present


def test_director_selected_speaker_and_listener_are_present():
    state = {
        "location_state": {"current_location_id": "loc_tavern"},
        "present_npc_state": {
            "loc_tavern": ["npc:Bran", "npc:Mira"]
        },
        "quest_state": {
            "quests": [
                {
                    "quest_id": "quest:old_mill_bandits",
                    "title": "Trouble near the Old Mill",
                    "summary": "There is talk of armed figures near the old mill road.",
                    "status": "active",
                    "location_id": "loc_tavern",
                }
            ]
        },
    }

    intent = select_conversation_intent(
        state,
        settings={"conversation_director_cooldown_ticks": 4},
        tick=100,
    )

    assert intent["selected"] is True
    assert intent["speaker_id"] in {"npc:Bran", "npc:Mira"}
    assert intent["listener_id"] in {"npc:Bran", "npc:Mira"}
    assert intent["speaker_id"] != intent["listener_id"]
    assert intent["topic_type"] == "quest"
