"""Living-world ambient system tests.

Tests for:
- Ambient builder: update extraction, salience scoring, visibility filter, coalescing, queue
- Ambient dialogue: candidate building, cooldown selection, cooldown application
- Ambient policy: interruption decisions, delivery classification
- Ambient narration: template fallback, LLM narration
- Idle tick: runtime idle advancement
- Resume catch-up: bounded catch-up on reconnect

Run with:
    cd src && PYTHONPATH="." python3 -m pytest tests/unit/rpg/test_living_world.py -v --noconftest
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, SRC_DIR)


# ── Helpers ────────────────────────────────────────────────────────────────

def _minimal_session(
    *,
    session_id: str = "test-session-001",
    player_location: str = "loc:market",
    tick: int = 5,
) -> Dict[str, Any]:
    """Build a minimal valid session dict for testing."""
    return {
        "manifest": {"id": session_id, "schema_version": 4},
        "setup_payload": {"metadata": {"simulation_state": {}}},
        "simulation_state": {
            "tick": tick,
            "player_state": {
                "location_id": player_location,
                "nearby_npc_ids": ["npc:guard", "npc:merchant"],
            },
            "events": [],
            "npc_decisions": {},
            "npc_index": {
                "npc:guard": {"name": "Guard Captain", "location_id": "loc:market"},
                "npc:merchant": {"name": "Merchant", "location_id": "loc:market"},
                "npc:thief": {"name": "Thief", "location_id": "loc:alley"},
            },
            "npc_minds": {},
            "factions": {},
            "incidents": [],
        },
        "runtime_state": {
            "tick": tick,
            "current_scene": {"scene_id": "scene:market", "location_id": "loc:market"},
            "ambient_queue": [],
            "ambient_seq": 0,
            "last_idle_tick_at": "",
            "last_player_turn_at": "",
            "idle_streak": 0,
            "ambient_cooldowns": {},
            "recent_ambient_ids": [],
            "pending_interrupt": None,
            "subscription_state": {"last_polled_seq": 0},
            "ambient_metrics": {"emitted": 0, "suppressed": 0, "coalesced": 0},
        },
    }


def _make_update(**kwargs) -> Dict[str, Any]:
    """Shorthand for building ambient updates."""
    from app.rpg.session.ambient_builder import make_ambient_update
    return make_ambient_update(**kwargs)


# ════════════════════════════════════════════════════════════════════════════
# 1. Ambient Builder Tests
# ════════════════════════════════════════════════════════════════════════════

class TestAmbientUpdateContract:
    """Verify ambient update structure."""

    def test_blank_update_has_all_fields(self):
        from app.rpg.session.ambient_builder import _blank_ambient_update
        blank = _blank_ambient_update()
        required = [
            "ambient_id", "seq", "tick", "kind", "priority", "interrupt",
            "speaker_id", "speaker_name", "target_id", "target_name",
            "scene_id", "location_id", "text", "structured", "source_event_ids",
            "source", "created_at",
        ]
        for key in required:
            assert key in blank, f"Missing required field: {key}"

    def test_make_ambient_update_fills_defaults(self):
        update = _make_update(kind="world_event", text="Test event")
        assert update["kind"] == "world_event"
        assert update["text"] == "Test event"
        assert update["seq"] == 0
        assert update["created_at"]  # Not empty

    def test_make_ambient_update_ignores_unknown_keys(self):
        update = _make_update(kind="world_event", unknown_field="ignored")
        assert "unknown_field" not in update


class TestEnsureAmbientRuntimeState:
    """Verify runtime state normalization."""

    def test_empty_dict_gets_all_defaults(self):
        from app.rpg.session.ambient_builder import ensure_ambient_runtime_state
        state = ensure_ambient_runtime_state({})
        assert state["ambient_queue"] == []
        assert state["ambient_seq"] == 0
        assert state["idle_streak"] == 0
        assert state["ambient_cooldowns"] == {}
        assert "subscription_state" in state
        assert "ambient_metrics" in state

    def test_existing_values_preserved(self):
        from app.rpg.session.ambient_builder import ensure_ambient_runtime_state
        state = ensure_ambient_runtime_state({"ambient_seq": 42, "idle_streak": 3})
        assert state["ambient_seq"] == 42
        assert state["idle_streak"] == 3

    def test_non_dict_returns_defaults(self):
        from app.rpg.session.ambient_builder import ensure_ambient_runtime_state
        state = ensure_ambient_runtime_state(None)
        assert isinstance(state, dict)
        assert state["ambient_seq"] == 0


class TestNormalizeAmbientState:
    """Verify bounded trimming."""

    def test_queue_trimmed_to_max(self):
        from app.rpg.session.ambient_builder import (
            _MAX_AMBIENT_QUEUE,
            normalize_ambient_state,
        )
        state = {"ambient_queue": [{"seq": i} for i in range(50)]}
        result = normalize_ambient_state(state)
        assert len(result["ambient_queue"]) <= _MAX_AMBIENT_QUEUE

    def test_recent_ids_trimmed(self):
        from app.rpg.session.ambient_builder import (
            _MAX_RECENT_AMBIENT_IDS,
            normalize_ambient_state,
        )
        state = {"recent_ambient_ids": [f"id:{i}" for i in range(100)]}
        result = normalize_ambient_state(state)
        assert len(result["recent_ambient_ids"]) <= _MAX_RECENT_AMBIENT_IDS

    def test_cooldowns_trimmed(self):
        from app.rpg.session.ambient_builder import (
            _MAX_AMBIENT_COOLDOWNS,
            normalize_ambient_state,
        )
        state = {"ambient_cooldowns": {f"key:{i}": i for i in range(100)}}
        result = normalize_ambient_state(state)
        assert len(result["ambient_cooldowns"]) <= _MAX_AMBIENT_COOLDOWNS


class TestBuildAmbientUpdates:
    """Verify extraction from simulation state diffs."""

    def test_new_events_extracted(self):
        from app.rpg.session.ambient_builder import build_ambient_updates
        before = {"events": [], "tick": 5, "player_state": {"location_id": "loc:market", "nearby_npc_ids": []}, "npc_decisions": {}, "npc_index": {}, "factions": {}, "incidents": []}
        after = dict(before)
        after["events"] = [{"event_id": "evt:1", "location_id": "loc:market", "description": "A fire breaks out."}]
        after["tick"] = 6
        updates = build_ambient_updates(before, after, {})
        assert len(updates) >= 1
        assert any(u["kind"] == "world_event" for u in updates)

    def test_npc_arrival_detected(self):
        from app.rpg.session.ambient_builder import build_ambient_updates
        before = {"events": [], "tick": 5, "player_state": {"location_id": "loc:market", "nearby_npc_ids": ["npc:guard"]}, "npc_decisions": {}, "npc_index": {"npc:thief": {"name": "Thief", "location_id": "loc:alley"}}, "factions": {}, "incidents": []}
        after = dict(before)
        after["npc_decisions"] = {"npc:thief": {"action": "move", "target_location": "loc:market", "location_id": "loc:alley"}}
        after["tick"] = 6
        updates = build_ambient_updates(before, after, {})
        assert any(u["kind"] == "arrival" for u in updates)

    def test_no_updates_if_no_changes(self):
        from app.rpg.session.ambient_builder import build_ambient_updates
        state = {"events": [], "tick": 5, "player_state": {"location_id": "loc:market", "nearby_npc_ids": []}, "npc_decisions": {}, "npc_index": {}, "factions": {}, "incidents": []}
        updates = build_ambient_updates(state, state, {})
        assert updates == []

    def test_combat_start_detected(self):
        from app.rpg.session.ambient_builder import build_ambient_updates
        before = {"events": [], "tick": 5, "player_state": {"location_id": "loc:market", "nearby_npc_ids": ["npc:guard"]}, "npc_decisions": {}, "npc_index": {"npc:guard": {"name": "Guard", "location_id": "loc:market"}}, "factions": {}, "incidents": []}
        after = dict(before)
        after["npc_decisions"] = {"npc:guard": {"action": "attack", "target_id": "player", "text": "The guard attacks!"}}
        after["tick"] = 6
        updates = build_ambient_updates(before, after, {})
        assert any(u["kind"] == "combat_start" for u in updates)


class TestSalienceScoring:
    """Verify deterministic salience scoring."""

    def test_same_location_bonus(self):
        from app.rpg.session.ambient_builder import score_ambient_salience
        update = _make_update(kind="world_event", location_id="loc:market", priority=0.5)
        ctx = {"player_location": "loc:market", "nearby_npc_ids": [], "recent_ambient_ids": []}
        score = score_ambient_salience(update, ctx)
        assert score > 0.5  # Got location bonus

    def test_player_target_bonus(self):
        from app.rpg.session.ambient_builder import score_ambient_salience
        update = _make_update(kind="npc_to_player", target_id="player", priority=0.3)
        ctx = {"player_location": "", "nearby_npc_ids": [], "recent_ambient_ids": []}
        score = score_ambient_salience(update, ctx)
        assert score >= 0.7  # Player target bonus

    def test_repetition_penalty(self):
        from app.rpg.session.ambient_builder import score_ambient_salience
        update = _make_update(kind="world_event", priority=0.5, source_event_ids=["evt:1"])
        ctx_fresh = {"player_location": "", "nearby_npc_ids": [], "recent_ambient_ids": []}
        ctx_repeat = {"player_location": "", "nearby_npc_ids": [], "recent_ambient_ids": ["evt:1"]}
        score_fresh = score_ambient_salience(update, ctx_fresh)
        score_repeat = score_ambient_salience(update, ctx_repeat)
        assert score_repeat < score_fresh

    def test_score_bounded(self):
        from app.rpg.session.ambient_builder import score_ambient_salience
        update = _make_update(kind="combat_start", target_id="player", interrupt=True, priority=2.0, location_id="loc:x")
        ctx = {"player_location": "loc:x", "nearby_npc_ids": ["npc:x"], "recent_ambient_ids": []}
        update["speaker_id"] = "npc:x"
        score = score_ambient_salience(update, ctx)
        assert 0.0 <= score <= 3.0


class TestVisibilityFilter:
    """Verify update visibility filtering."""

    def test_npc_to_player_always_visible(self):
        from app.rpg.session.ambient_builder import is_player_visible_update
        update = _make_update(kind="npc_to_player")
        session = _minimal_session()
        assert is_player_visible_update(update, session) is True

    def test_distant_event_filtered(self):
        from app.rpg.session.ambient_builder import is_player_visible_update
        update = _make_update(kind="world_event", location_id="loc:far_away", priority=0.3)
        session = _minimal_session(player_location="loc:market")
        assert is_player_visible_update(update, session) is False

    def test_system_summary_always_visible(self):
        from app.rpg.session.ambient_builder import is_player_visible_update
        update = _make_update(kind="system_summary")
        session = _minimal_session()
        assert is_player_visible_update(update, session) is True

    def test_very_low_priority_filtered(self):
        from app.rpg.session.ambient_builder import is_player_visible_update
        update = _make_update(kind="world_event", location_id="loc:market", priority=0.05)
        session = _minimal_session(player_location="loc:market")
        assert is_player_visible_update(update, session) is False


class TestCoalescing:
    """Verify update coalescing merges repetitive updates."""

    def test_npc_chatter_capped(self):
        from app.rpg.session.ambient_builder import coalesce_ambient_updates
        updates = [
            _make_update(kind="npc_to_npc", priority=0.3, speaker_id=f"npc:{i}", text=f"Chat {i}")
            for i in range(5)
        ]
        result = coalesce_ambient_updates(updates, {})
        npc_chatter = [u for u in result if u["kind"] == "npc_to_npc"]
        assert len(npc_chatter) <= 2

    def test_low_world_coalesced(self):
        from app.rpg.session.ambient_builder import coalesce_ambient_updates
        updates = [
            _make_update(kind="world_event", priority=0.1, text=f"Event {i}")
            for i in range(5)
        ]
        result = coalesce_ambient_updates(updates, {})
        assert len(result) < 5  # Should be coalesced

    def test_high_priority_preserved(self):
        from app.rpg.session.ambient_builder import coalesce_ambient_updates
        updates = [
            _make_update(kind="combat_start", priority=0.9, text="Combat!"),
            _make_update(kind="npc_to_player", priority=0.8, text="Hello!"),
        ]
        result = coalesce_ambient_updates(updates, {})
        assert len(result) == 2

    def test_empty_input(self):
        from app.rpg.session.ambient_builder import coalesce_ambient_updates
        assert coalesce_ambient_updates([], {}) == []


class TestAmbientQueue:
    """Verify queue operations."""

    def test_enqueue_assigns_seq(self):
        from app.rpg.session.ambient_builder import (
            enqueue_ambient_updates,
            ensure_ambient_runtime_state,
        )
        state = ensure_ambient_runtime_state({})
        updates = [_make_update(kind="world_event", text="Test")]
        state = enqueue_ambient_updates(state, updates)
        assert state["ambient_seq"] == 1
        assert len(state["ambient_queue"]) == 1
        assert state["ambient_queue"][0]["ambient_id"] == "ambient:1"

    def test_enqueue_increments_seq(self):
        from app.rpg.session.ambient_builder import (
            enqueue_ambient_updates,
            ensure_ambient_runtime_state,
        )
        state = ensure_ambient_runtime_state({"ambient_seq": 10})
        updates = [_make_update(kind="world_event", text="A"), _make_update(kind="arrival", text="B")]
        state = enqueue_ambient_updates(state, updates)
        assert state["ambient_seq"] == 12
        assert len(state["ambient_queue"]) == 2

    def test_queue_bounded(self):
        from app.rpg.session.ambient_builder import (
            _MAX_AMBIENT_QUEUE,
            enqueue_ambient_updates,
            ensure_ambient_runtime_state,
        )
        state = ensure_ambient_runtime_state({})
        big_batch = [_make_update(kind="world_event", text=f"E{i}") for i in range(50)]
        state = enqueue_ambient_updates(state, big_batch)
        assert len(state["ambient_queue"]) <= _MAX_AMBIENT_QUEUE

    def test_get_pending_after_seq(self):
        from app.rpg.session.ambient_builder import (
            enqueue_ambient_updates,
            ensure_ambient_runtime_state,
            get_pending_ambient_updates,
        )
        state = ensure_ambient_runtime_state({})
        updates = [_make_update(kind="world_event", text=f"E{i}") for i in range(5)]
        state = enqueue_ambient_updates(state, updates)
        session = {"runtime_state": state}
        pending = get_pending_ambient_updates(session, after_seq=2, limit=8)
        assert len(pending) == 3  # seq 3,4,5
        assert all(p["seq"] > 2 for p in pending)

    def test_get_pending_respects_limit(self):
        from app.rpg.session.ambient_builder import (
            enqueue_ambient_updates,
            ensure_ambient_runtime_state,
            get_pending_ambient_updates,
        )
        state = ensure_ambient_runtime_state({})
        updates = [_make_update(kind="world_event", text=f"E{i}") for i in range(10)]
        state = enqueue_ambient_updates(state, updates)
        session = {"runtime_state": state}
        pending = get_pending_ambient_updates(session, after_seq=0, limit=3)
        assert len(pending) == 3

    def test_acknowledge_updates(self):
        from app.rpg.session.ambient_builder import (
            acknowledge_ambient_updates,
            ensure_ambient_runtime_state,
        )
        state = ensure_ambient_runtime_state({"ambient_seq": 10})
        session = {"runtime_state": state}
        session = acknowledge_ambient_updates(session, up_to_seq=7)
        assert session["runtime_state"]["subscription_state"]["last_polled_seq"] == 7

    def test_metrics_track_emitted(self):
        from app.rpg.session.ambient_builder import (
            enqueue_ambient_updates,
            ensure_ambient_runtime_state,
        )
        state = ensure_ambient_runtime_state({})
        updates = [_make_update(kind="world_event", text="Test")]
        state = enqueue_ambient_updates(state, updates)
        assert state["ambient_metrics"]["emitted"] == 1


# ════════════════════════════════════════════════════════════════════════════
# 2. Ambient Dialogue Tests
# ════════════════════════════════════════════════════════════════════════════

class TestBuildDialogueCandidates:
    """Verify candidate generation from simulation state."""

    def test_generates_candidates_for_nearby_npcs(self):
        from app.rpg.ai.ambient_dialogue import build_ambient_dialogue_candidates
        sim = {
            "tick": 5,
            "npc_index": {
                "npc:guard": {"name": "Guard", "location_id": "loc:market"},
            },
            "npc_minds": {
                "npc:guard": {
                    "beliefs": {"player": {"trust": 0.5, "hostility": 0.0}},
                    "goals": [],
                },
            },
            "npc_decisions": {},
        }
        runtime = {"tick": 5, "ambient_cooldowns": {}}
        ctx = {"player_location": "loc:market", "nearby_npc_ids": ["npc:guard"]}
        candidates = build_ambient_dialogue_candidates(sim, runtime, ctx)
        assert len(candidates) >= 1
        assert any(c["kind"] == "npc_to_player" for c in candidates)

    def test_hostile_npc_generates_warning(self):
        from app.rpg.ai.ambient_dialogue import build_ambient_dialogue_candidates
        sim = {
            "tick": 5,
            "npc_index": {"npc:bandit": {"name": "Bandit", "location_id": "loc:market"}},
            "npc_minds": {
                "npc:bandit": {
                    "beliefs": {"player": {"trust": -0.5, "hostility": 0.8}},
                    "goals": [],
                },
            },
            "npc_decisions": {},
        }
        runtime = {"tick": 5, "ambient_cooldowns": {}}
        ctx = {"player_location": "loc:market", "nearby_npc_ids": ["npc:bandit"]}
        candidates = build_ambient_dialogue_candidates(sim, runtime, ctx)
        assert any(c["kind"] in ("warning", "taunt") for c in candidates)

    def test_no_candidates_for_distant_npcs(self):
        from app.rpg.ai.ambient_dialogue import build_ambient_dialogue_candidates
        sim = {
            "tick": 5,
            "npc_index": {"npc:far": {"name": "Far NPC", "location_id": "loc:faraway"}},
            "npc_minds": {"npc:far": {"beliefs": {"player": {"trust": 0.9}}, "goals": []}},
            "npc_decisions": {},
        }
        runtime = {"tick": 5, "ambient_cooldowns": {}}
        ctx = {"player_location": "loc:market", "nearby_npc_ids": []}
        candidates = build_ambient_dialogue_candidates(sim, runtime, ctx)
        assert len(candidates) == 0


class TestDialogueCooldowns:
    """Verify cooldown-aware selection."""

    def test_selection_respects_speaker_cooldown(self):
        from app.rpg.ai.ambient_dialogue import select_ambient_dialogue_candidate
        candidates = [
            {"kind": "npc_to_player", "speaker_id": "npc:guard", "salience": 0.8, "target_id": "player"},
        ]
        # NPC just spoke at tick 5, current tick is 6 (within cooldown of 3)
        runtime = {"tick": 6, "ambient_cooldowns": {"speaker:npc:guard": 5}}
        result = select_ambient_dialogue_candidate(candidates, runtime)
        assert result is None  # On cooldown

    def test_selection_picks_highest_salience(self):
        from app.rpg.ai.ambient_dialogue import select_ambient_dialogue_candidate
        candidates = [
            {"kind": "gossip", "speaker_id": "npc:a", "salience": 0.2, "target_id": ""},
            {"kind": "npc_to_player", "speaker_id": "npc:b", "salience": 0.9, "target_id": "player"},
        ]
        runtime = {"tick": 10, "ambient_cooldowns": {}}
        result = select_ambient_dialogue_candidate(candidates, runtime)
        assert result is not None
        assert result["speaker_id"] == "npc:b"

    def test_cooldown_application(self):
        from app.rpg.ai.ambient_dialogue import apply_dialogue_cooldowns
        candidate = {"speaker_id": "npc:guard", "kind": "npc_to_player", "target_id": "player"}
        runtime = {"tick": 10, "ambient_cooldowns": {}}
        runtime = apply_dialogue_cooldowns(runtime, candidate)
        assert "speaker:npc:guard" in runtime["ambient_cooldowns"]
        assert "kind:npc_to_player" in runtime["ambient_cooldowns"]
        assert "pair:npc:guard:player" in runtime["ambient_cooldowns"]

    def test_deterministic_ordering(self):
        from app.rpg.ai.ambient_dialogue import select_ambient_dialogue_candidate
        candidates = [
            {"kind": "npc_to_player", "speaker_id": "npc:b", "salience": 0.5, "target_id": "player"},
            {"kind": "npc_to_player", "speaker_id": "npc:a", "salience": 0.5, "target_id": "player"},
        ]
        runtime = {"tick": 20, "ambient_cooldowns": {}}
        # Same salience — should pick alphabetically first by speaker_id
        r1 = select_ambient_dialogue_candidate(candidates, runtime)
        r2 = select_ambient_dialogue_candidate(candidates, runtime)
        assert r1["speaker_id"] == r2["speaker_id"]


class TestDialogueRequest:
    """Verify dialogue request building."""

    def test_request_structure(self):
        from app.rpg.ai.ambient_dialogue import build_ambient_dialogue_request
        candidate = {
            "kind": "npc_to_player",
            "speaker_id": "npc:guard",
            "speaker_name": "Guard",
            "target_id": "player",
            "target_name": "you",
            "text_hint": "Guard wants to speak.",
            "emotion": "friendly",
            "location_id": "loc:market",
            "tick": 5,
        }
        request = build_ambient_dialogue_request(candidate, {"scene_id": "scene:market"})
        assert request["kind"] == "npc_to_player"
        assert request["speaker_name"] == "Guard"
        assert request["scene_id"] == "scene:market"


# ════════════════════════════════════════════════════════════════════════════
# 3. Ambient Policy Tests
# ════════════════════════════════════════════════════════════════════════════

class TestInterruptionPolicy:
    """Verify interruption decisions."""

    def test_combat_always_interrupts(self):
        from app.rpg.session.ambient_policy import should_interrupt_player
        update = _make_update(kind="combat_start", priority=0.9)
        session = _minimal_session()
        assert should_interrupt_player(session, update) is True

    def test_gossip_never_interrupts(self):
        from app.rpg.session.ambient_policy import should_interrupt_player
        update = _make_update(kind="gossip", priority=0.2)
        session = _minimal_session()
        assert should_interrupt_player(session, update) is False

    def test_system_summary_no_interrupt(self):
        from app.rpg.session.ambient_policy import should_interrupt_player
        update = _make_update(kind="system_summary", priority=0.5)
        session = _minimal_session()
        assert should_interrupt_player(session, update) is False

    def test_npc_to_player_interrupts_high_priority(self):
        from app.rpg.session.ambient_policy import should_interrupt_player
        update = _make_update(kind="npc_to_player", target_id="player", priority=0.6)
        session = _minimal_session()
        assert should_interrupt_player(session, update) is True

    def test_rate_limiting(self):
        from app.rpg.session.ambient_policy import should_interrupt_player
        update = _make_update(kind="npc_to_player", target_id="player", priority=0.6)
        session = _minimal_session(tick=10)
        session["runtime_state"]["last_interrupt_tick"] = 9  # Just had one
        assert should_interrupt_player(session, update) is False

    def test_warning_interrupts(self):
        from app.rpg.session.ambient_policy import should_interrupt_player
        update = _make_update(kind="warning", priority=0.7)
        session = _minimal_session()
        assert should_interrupt_player(session, update) is True


class TestDeliveryClassification:
    """Verify delivery mode classification."""

    def test_combat_while_typing_still_interrupts(self):
        from app.rpg.session.ambient_policy import classify_ambient_delivery
        update = _make_update(kind="combat_start", priority=0.9)
        session = _minimal_session()
        assert classify_ambient_delivery(session, update, is_typing=True) == "interrupt"

    def test_npc_speech_while_typing_becomes_badge(self):
        from app.rpg.session.ambient_policy import classify_ambient_delivery
        update = _make_update(kind="npc_to_player", target_id="player", priority=0.6)
        session = _minimal_session()
        result = classify_ambient_delivery(session, update, is_typing=True)
        assert result == "badge"

    def test_low_priority_is_silent(self):
        from app.rpg.session.ambient_policy import classify_ambient_delivery
        update = _make_update(kind="world_event", priority=0.1)
        session = _minimal_session()
        assert classify_ambient_delivery(session, update) == "silent"

    def test_medium_priority_is_badge(self):
        from app.rpg.session.ambient_policy import classify_ambient_delivery
        update = _make_update(kind="world_event", priority=0.5)
        session = _minimal_session()
        result = classify_ambient_delivery(session, update)
        assert result in ("badge", "interrupt")


class TestRecordInterrupt:
    """Verify interrupt recording."""

    def test_records_interrupt(self):
        from app.rpg.session.ambient_policy import record_interrupt
        update = _make_update(kind="combat_start", text="Combat!", ambient_id="ambient:5")
        session = _minimal_session()
        session = record_interrupt(session, update)
        pi = session["runtime_state"]["pending_interrupt"]
        assert pi is not None
        assert pi["kind"] == "combat_start"


# ════════════════════════════════════════════════════════════════════════════
# 4. Ambient Narration Tests
# ════════════════════════════════════════════════════════════════════════════

class TestAmbientNarration:
    """Verify narrate_ambient_update in world_scene_narrator."""

    def test_template_fallback_no_llm(self):
        from app.rpg.ai.world_scene_narrator import narrate_ambient_update
        update = _make_update(
            kind="npc_to_player",
            speaker_id="npc:guard",
            speaker_name="Guard",
            text="Halt! Who goes there?",
        )
        result = narrate_ambient_update(
            ambient_update=update,
            simulation_state={},
            current_scene={"summary": "A busy market."},
        )
        assert "Guard" in result["text"]
        assert result["used_app_llm"] is False
        assert len(result["speaker_turns"]) >= 1

    def test_world_event_template(self):
        from app.rpg.ai.world_scene_narrator import narrate_ambient_update
        update = _make_update(kind="world_event", text="Rain begins to fall.")
        result = narrate_ambient_update(
            ambient_update=update,
            simulation_state={},
            current_scene={},
        )
        assert "Rain" in result["text"]
        assert result["speaker_turns"] == []  # No speaker for world events

    def test_system_summary_template(self):
        from app.rpg.ai.world_scene_narrator import narrate_ambient_update
        update = _make_update(kind="system_summary", text="3 events occurred.")
        result = narrate_ambient_update(
            ambient_update=update,
            simulation_state={},
            current_scene={},
        )
        assert "3 events" in result["text"]

    def test_llm_path_used_when_available(self):
        from app.rpg.ai.world_scene_narrator import narrate_ambient_update
        mock_gateway = MagicMock()
        mock_gateway.call.return_value = "The guard glares at you suspiciously."

        update = _make_update(
            kind="npc_to_player",
            speaker_name="Guard",
            text="Stop right there.",
        )
        result = narrate_ambient_update(
            ambient_update=update,
            simulation_state={},
            current_scene={"summary": "A tense checkpoint."},
            llm_gateway=mock_gateway,
        )
        assert result["used_app_llm"] is True
        assert result["raw_llm_narrative"] != ""

    def test_llm_error_falls_back_to_template(self):
        from app.rpg.ai.world_scene_narrator import narrate_ambient_update
        mock_gateway = MagicMock()
        mock_gateway.call.return_value = "[ERROR: timeout]"

        update = _make_update(
            kind="npc_to_player",
            speaker_name="Guard",
            text="Stop!",
        )
        result = narrate_ambient_update(
            ambient_update=update,
            simulation_state={},
            current_scene={},
            llm_gateway=mock_gateway,
        )
        assert result["used_app_llm"] is False
        assert "Guard" in result["text"]

    def test_all_dialogue_kinds_produce_speaker_turns(self):
        from app.rpg.ai.world_scene_narrator import narrate_ambient_update
        dialogue_kinds = ["npc_to_player", "npc_to_npc", "companion_comment", "warning", "taunt", "gossip"]
        for kind in dialogue_kinds:
            update = _make_update(kind=kind, speaker_id="npc:test", speaker_name="TestNPC", text="Test line.")
            result = narrate_ambient_update(
                ambient_update=update,
                simulation_state={},
                current_scene={},
            )
            assert len(result["speaker_turns"]) >= 1, f"Kind '{kind}' should produce speaker turns"
            assert result["speaker_turns"][0].get("ambient") is True


# ════════════════════════════════════════════════════════════════════════════
# 5. Migration + Save/Load Tests
# ════════════════════════════════════════════════════════════════════════════

class TestMigration:
    """Verify old sessions gain ambient state."""

    def test_v3_session_migrated(self):
        from app.rpg.session.migrations import migrate_session_payload
        old_session = {
            "manifest": {"id": "test", "schema_version": 3},
            "simulation_state": {},
            "runtime_state": {"tick": 5},
        }
        migrated = migrate_session_payload(old_session)
        rt = migrated.get("runtime_state", {})
        assert "ambient_queue" in rt
        assert "ambient_seq" in rt
        assert rt["ambient_seq"] == 0

    def test_v4_session_no_change(self):
        from app.rpg.session.migrations import migrate_session_payload
        session = _minimal_session()
        session["manifest"]["schema_version"] = 4
        session["runtime_state"]["ambient_seq"] = 42
        migrated = migrate_session_payload(session)
        assert migrated["runtime_state"]["ambient_seq"] == 42

    def test_service_normalize_adds_ambient(self):
        from app.rpg.session.service import create_or_normalize_session
        session = {
            "manifest": {"id": "test", "schema_version": 3},
            "simulation_state": {},
            "runtime_state": {"tick": 5},
        }
        normalized = create_or_normalize_session(session)
        rt = normalized.get("runtime_state", {})
        assert "ambient_queue" in rt
        assert "ambient_metrics" in rt


# ════════════════════════════════════════════════════════════════════════════
# 6. Hard Caps Verification
# ════════════════════════════════════════════════════════════════════════════

class TestHardCaps:
    """Verify all bounded state invariants."""

    def test_caps_are_positive_integers(self):
        from app.rpg.session.ambient_builder import (
            _MAX_AMBIENT_BATCH_PER_DELIVERY,
            _MAX_AMBIENT_COOLDOWNS,
            _MAX_AMBIENT_QUEUE,
            _MAX_IDLE_TICKS_PER_REQUEST,
            _MAX_RECENT_AMBIENT_IDS,
            _MAX_RESUME_CATCHUP_TICKS,
        )
        for cap in [_MAX_AMBIENT_QUEUE, _MAX_RECENT_AMBIENT_IDS, _MAX_AMBIENT_COOLDOWNS,
                     _MAX_IDLE_TICKS_PER_REQUEST, _MAX_RESUME_CATCHUP_TICKS, _MAX_AMBIENT_BATCH_PER_DELIVERY]:
            assert isinstance(cap, int) and cap > 0

    def test_delivery_limit_respected(self):
        from app.rpg.session.ambient_builder import (
            _MAX_AMBIENT_BATCH_PER_DELIVERY,
            enqueue_ambient_updates,
            ensure_ambient_runtime_state,
            get_pending_ambient_updates,
        )
        state = ensure_ambient_runtime_state({})
        updates = [_make_update(kind="world_event", text=f"E{i}") for i in range(20)]
        state = enqueue_ambient_updates(state, updates)
        session = {"runtime_state": state}
        pending = get_pending_ambient_updates(session, after_seq=0, limit=100)
        assert len(pending) <= _MAX_AMBIENT_BATCH_PER_DELIVERY
