"""RPG-design system tests.

Tests for:
- NPC initiative: candidate building, selection, cooldowns, opening relevance
- World behavior bias: config-driven salience adjustments
- World event director: candidate building, filtering, behavior adjustments, ambient conversion
- World behavior config: normalize, validate, from_dict/to_dict roundtrip, genre defaults
- Ambient policy: quiet window, urgent events, new kind classification
- Runtime helpers: idle tick, opening runtime, initiative update conversion
- Ambient builder extensions: new kinds visibility, salience, coalescing

Run with:
    cd src && PYTHONPATH="." python3 -m pytest tests/unit/rpg/test_rpg_design.py -v --noconftest
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import machinery — stub all app.* dependencies that we don't test,
# then load real modules by file path to bypass app/__init__.py (flask).
# ---------------------------------------------------------------------------

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, SRC_DIR)

_REAL_MODULES = {
    "app.rpg.creator.schema",
    "app.rpg.creator.defaults",
    "app.rpg.creator.validation",
    "app.rpg.ai.npc_initiative",
    "app.rpg.world.world_event_director",
    "app.rpg.session.ambient_builder",
    "app.rpg.session.ambient_policy",
    "app.rpg.session.runtime",
}


class _StubModule(types.ModuleType):
    """Auto-stub module that returns MagicMock for unknown attributes."""

    def __init__(self, name: str):
        super().__init__(name)
        self.__path__: list = []
        self.__package__ = name
        self.__file__ = "<stub>"
        self.__loader__ = None

    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return MagicMock()


class _StubLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return _StubModule(spec.name)

    def exec_module(self, module):
        pass


class _AppStubFinder(importlib.abc.MetaPathFinder):
    """Intercept all ``app.*`` imports and stub anything not in _REAL_MODULES."""

    def find_spec(self, fullname, path, target=None):
        if not fullname.startswith("app"):
            return None
        if fullname in _REAL_MODULES:
            return None
        if fullname in sys.modules:
            return None
        return importlib.machinery.ModuleSpec(
            fullname, _StubLoader(), is_package=True,
        )


sys.meta_path.insert(0, _AppStubFinder())


def _load(mod_name: str, rel_path: str):
    """Load a real module by file path, bypassing package __init__.py."""
    sys.modules.pop(mod_name, None)
    spec = importlib.util.spec_from_file_location(
        mod_name, os.path.join(SRC_DIR, rel_path),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load real modules (order matters: dependencies first)
_schema = _load("app.rpg.creator.schema", "app/rpg/creator/schema.py")
_defaults = _load("app.rpg.creator.defaults", "app/rpg/creator/defaults.py")
_validation = _load("app.rpg.creator.validation", "app/rpg/creator/validation.py")
_npc_init = _load("app.rpg.ai.npc_initiative", "app/rpg/ai/npc_initiative.py")
_wed = _load("app.rpg.world.world_event_director", "app/rpg/world/world_event_director.py")
_amb_builder = _load("app.rpg.session.ambient_builder", "app/rpg/session/ambient_builder.py")
_amb_policy = _load("app.rpg.session.ambient_policy", "app/rpg/session/ambient_policy.py")
_runtime = _load("app.rpg.session.runtime", "app/rpg/session/runtime.py")

# ── Module-level aliases for tested functions ─────────────────────────────

build_npc_initiative_candidates = _npc_init.build_npc_initiative_candidates
select_npc_initiative_candidate = _npc_init.select_npc_initiative_candidate
apply_initiative_cooldowns = _npc_init.apply_initiative_cooldowns
compute_opening_relevance = _npc_init.compute_opening_relevance
apply_world_behavior_bias = _npc_init.apply_world_behavior_bias
MAX_INITIATIVE_CANDIDATES = _npc_init.MAX_INITIATIVE_CANDIDATES

build_world_event_candidates = _wed.build_world_event_candidates
filter_world_events = _wed.filter_world_events
apply_world_behavior_to_events = _wed.apply_world_behavior_to_events
convert_events_to_ambient_updates = _wed.convert_events_to_ambient_updates
MAX_WORLD_EVENTS_PER_TICK = _wed.MAX_WORLD_EVENTS_PER_TICK

normalize_world_behavior_config = _schema.normalize_world_behavior_config
WorldBehaviorConfig = _schema.WorldBehaviorConfig

infer_default_world_behavior = _defaults.infer_default_world_behavior

validate_world_behavior = _validation.validate_world_behavior

should_interrupt_player = _amb_policy.should_interrupt_player
classify_ambient_delivery = _amb_policy.classify_ambient_delivery

is_player_visible_update = _amb_builder.is_player_visible_update
score_ambient_salience = _amb_builder.score_ambient_salience
coalesce_ambient_updates = _amb_builder.coalesce_ambient_updates

compute_idle_tick_count = _runtime.compute_idle_tick_count
get_effective_world_behavior = _runtime.get_effective_world_behavior
_build_opening_runtime = _runtime._build_opening_runtime
_check_opening_resolution = _runtime._check_opening_resolution
_make_initiative_update_from_candidate = _runtime._make_initiative_update_from_candidate


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
        "setup_payload": {
            "metadata": {"simulation_state": {}},
            "world_behavior": {},
            "opening": {
                "scene_frame": "A busy market square",
                "immediate_problem": "A thief is on the loose",
                "player_involvement_reason": "You witnessed the theft",
                "present_npc_ids": ["npc:guard", "npc:merchant"],
                "first_choices": ["chase", "report"],
                "location_id": "loc:market",
            },
        },
        "simulation_state": {
            "tick": tick,
            "player_state": {
                "location_id": player_location,
                "nearby_npc_ids": ["npc:guard", "npc:merchant"],
            },
            "events": [],
            "npc_decisions": {},
            "npc_index": {
                "npc:guard": {"name": "Guard Captain", "location_id": "loc:market", "role": "guard"},
                "npc:merchant": {"name": "Merchant", "location_id": "loc:market", "role": "merchant"},
                "npc:thief": {"name": "Thief", "location_id": "loc:alley", "role": "rogue"},
            },
            "npc_minds": {},
            "factions": {},
            "faction_pressure": {},
            "incidents": [],
            "objectives": [],
            "resources": {},
            "environment": {},
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
            "opening_runtime": {
                "active": True,
                "present_npc_ids": ["npc:guard", "npc:merchant"],
                "starter_conflict": "thief_chase",
                "opening_resolved": False,
            },
            "post_player_quiet_ticks": 0,
            "turn_history": [],
        },
    }


def _player_context(
    *,
    player_location: str = "loc:market",
    nearby_npc_ids: list | None = None,
    player_idle: bool = False,
    active_conflict: str = "",
    recent_incidents: list | None = None,
    salient_events: list | None = None,
) -> Dict[str, Any]:
    return {
        "player_location": player_location,
        "nearby_npc_ids": nearby_npc_ids or ["npc:guard", "npc:merchant"],
        "player_idle": player_idle,
        "active_conflict": active_conflict,
        "recent_incidents": recent_incidents or [],
        "salient_events": salient_events or [],
    }


# ════════════════════════════════════════════════════════════════════════════
# 1. NPC Initiative Candidates
# ════════════════════════════════════════════════════════════════════════════


class TestNPCInitiativeCandidates:
    """Tests for build_npc_initiative_candidates()."""

    def test_hostile_npc_player_idle_generates_taunt(self):

        sim = {
            "tick": 5,
            "npc_index": {
                "npc:bandit": {"name": "Bandit", "location_id": "loc:market", "role": "enemy"},
            },
            "npc_minds": {
                "npc:bandit": {
                    "beliefs": {"player": {"trust": 0, "hostility": 0.8}},
                    "goals": [],
                },
            },
            "factions": {},
            "faction_pressure": {},
            "objectives": [],
        }
        ctx = _player_context(nearby_npc_ids=["npc:bandit"], player_idle=True)
        candidates = build_npc_initiative_candidates(sim, {}, ctx)

        taunt_or_warn = [c for c in candidates if c["kind"] in ("taunt", "warning")]
        assert taunt_or_warn, "Expected at least one taunt/warning candidate"
        assert taunt_or_warn[0]["speaker_id"] == "npc:bandit"
        assert taunt_or_warn[0]["target_id"] == "player"

    def test_hostile_npc_warning_for_moderate_hostility(self):

        sim = {
            "tick": 5,
            "npc_index": {
                "npc:bully": {"name": "Bully", "location_id": "loc:market", "role": "thug"},
            },
            "npc_minds": {
                "npc:bully": {
                    "beliefs": {"player": {"trust": 0, "hostility": 0.6}},
                    "goals": [],
                },
            },
            "factions": {},
            "faction_pressure": {},
            "objectives": [],
        }
        ctx = _player_context(nearby_npc_ids=["npc:bully"], player_idle=True)
        candidates = build_npc_initiative_candidates(sim, {}, ctx)
        warnings = [c for c in candidates if c["kind"] == "warning"]
        assert warnings, "Moderate hostility should generate a warning"

    def test_trusted_npc_conflict_generates_advice(self):

        sim = {
            "tick": 5,
            "npc_index": {
                "npc:sage": {"name": "Sage", "location_id": "loc:market", "role": "advisor"},
            },
            "npc_minds": {
                "npc:sage": {
                    "beliefs": {"player": {"trust": 0.6, "hostility": 0}},
                    "goals": [],
                },
            },
            "factions": {},
            "faction_pressure": {},
            "objectives": [],
        }
        ctx = _player_context(nearby_npc_ids=["npc:sage"], active_conflict="rebellion")
        candidates = build_npc_initiative_candidates(sim, {}, ctx)

        advice = [c for c in candidates if c["reason"] == "trusted_conflict_advice"]
        assert advice, "Trusted NPC + conflict should generate advice"
        assert advice[0]["action_intent"] == "advise"

    def test_faction_spike_generates_messenger_warning(self):

        sim = {
            "tick": 5,
            "npc_index": {
                "npc:herald": {"name": "Herald", "location_id": "loc:market", "role": "messenger"},
            },
            "npc_minds": {
                "npc:herald": {
                    "beliefs": {},
                    "goals": [],
                },
            },
            "factions": {},
            "faction_pressure": {
                "faction:rebels": {
                    "level": 0.9,
                    "location_id": "loc:market",
                    "messenger_ids": ["npc:herald"],
                },
            },
            "objectives": [],
        }
        ctx = _player_context(nearby_npc_ids=["npc:herald"])
        candidates = build_npc_initiative_candidates(sim, {}, ctx)

        messengers = [c for c in candidates if c["reason"] == "faction_pressure"]
        assert messengers, "Faction spike should generate messenger warning"
        assert messengers[0]["kind"] == "warning"
        assert messengers[0]["interrupt"] is True

    def test_objective_npc_generates_quest_prompt(self):

        sim = {
            "tick": 5,
            "npc_index": {
                "npc:questgiver": {"name": "Elder", "location_id": "loc:market", "role": "elder"},
            },
            "npc_minds": {
                "npc:questgiver": {"beliefs": {}, "goals": []},
            },
            "factions": {},
            "faction_pressure": {},
            "objectives": [
                {"related_npc_ids": ["npc:questgiver"], "description": "Find the lost artifact"},
            ],
        }
        ctx = _player_context(nearby_npc_ids=["npc:questgiver"])
        candidates = build_npc_initiative_candidates(sim, {}, ctx)

        quests = [c for c in candidates if c["kind"] == "quest_prompt"]
        assert quests, "Objective NPC should generate quest prompt"
        assert quests[0]["action_intent"] == "offer_quest"

    def test_companion_event_generates_companion_comment(self):

        sim = {
            "tick": 5,
            "npc_index": {
                "npc:ally": {"name": "Ally", "location_id": "loc:market", "role": "companion"},
            },
            "npc_minds": {
                "npc:ally": {"beliefs": {}, "goals": []},
            },
            "factions": {},
            "faction_pressure": {},
            "objectives": [],
        }
        ctx = _player_context(
            nearby_npc_ids=["npc:ally"],
            salient_events=[{"event_id": "evt1", "description": "explosion nearby"}],
        )
        candidates = build_npc_initiative_candidates(sim, {}, ctx)

        companion = [c for c in candidates if c["kind"] == "companion_comment"]
        assert companion, "Companion + salient event should generate companion comment"
        assert companion[0]["speaker_id"] == "npc:ally"

    def test_opening_npc_salience_boost(self):

        sim = {
            "tick": 5,
            "npc_index": {
                "npc:guard": {"name": "Guard", "location_id": "loc:market", "role": "guard"},
            },
            "npc_minds": {
                "npc:guard": {
                    "beliefs": {"player": {"trust": 0, "hostility": 0.8}},
                    "goals": [],
                },
            },
            "factions": {},
            "faction_pressure": {},
            "objectives": [],
        }
        runtime = {
            "opening_runtime": {
                "active": True,
                "present_npc_ids": ["npc:guard"],
                "starter_conflict": "thief_chase",
            },
        }
        ctx = _player_context(nearby_npc_ids=["npc:guard"], player_idle=True)
        candidates = build_npc_initiative_candidates(sim, runtime, ctx)

        opening_c = [c for c in candidates if c["speaker_id"] == "npc:guard"]
        assert opening_c
        # Opening NPC should have salience boost of +0.1
        assert opening_c[0]["salience"] > 0.6, "Opening NPC should have boosted salience"

    def test_max_candidates_cap(self):
        # Create more NPCs than the cap allows
        npc_index = {}
        npc_minds = {}
        nearby = []
        for i in range(40):
            nid = f"npc:{i}"
            npc_index[nid] = {"name": f"NPC_{i}", "location_id": "loc:market", "role": "companion"}
            npc_minds[nid] = {"beliefs": {}, "goals": []}
            nearby.append(nid)

        sim = {
            "tick": 5,
            "npc_index": npc_index,
            "npc_minds": npc_minds,
            "factions": {},
            "faction_pressure": {},
            "objectives": [],
        }
        ctx = _player_context(
            nearby_npc_ids=nearby,
            salient_events=[{"event_id": "e1"}],
        )
        candidates = build_npc_initiative_candidates(sim, {}, ctx)
        assert len(candidates) <= MAX_INITIATIVE_CANDIDATES

    def test_empty_state_returns_empty(self):

        candidates = build_npc_initiative_candidates({}, {}, {})
        assert candidates == []


# ════════════════════════════════════════════════════════════════════════════
# 2. NPC Initiative Selection
# ════════════════════════════════════════════════════════════════════════════


class TestNPCInitiativeSelection:
    """Tests for select_npc_initiative_candidate()."""

    def test_deterministic_ordering_salience_desc(self):

        candidates = [
            {"kind": "gossip", "salience": 0.3, "speaker_id": "npc:a", "target_id": "", "reason": "r1", "interrupt": False},
            {"kind": "warning", "salience": 0.8, "speaker_id": "npc:b", "target_id": "player", "reason": "r2", "interrupt": True},
            {"kind": "taunt", "salience": 0.6, "speaker_id": "npc:c", "target_id": "player", "reason": "r3", "interrupt": False},
        ]
        runtime = {"tick": 10, "ambient_cooldowns": {}, "opening_runtime": {"active": False}}
        selected = select_npc_initiative_candidate(candidates, runtime)

        assert selected is not None
        assert selected["speaker_id"] == "npc:b", "Should select highest salience first"

    def test_interrupt_first_when_salience_equal(self):

        candidates = [
            {"kind": "gossip", "salience": 0.7, "speaker_id": "npc:a", "target_id": "", "reason": "r1", "interrupt": False},
            {"kind": "warning", "salience": 0.7, "speaker_id": "npc:b", "target_id": "player", "reason": "r2", "interrupt": True},
        ]
        runtime = {"tick": 10, "ambient_cooldowns": {}, "opening_runtime": {"active": False}}
        selected = select_npc_initiative_candidate(candidates, runtime)

        assert selected is not None
        assert selected["interrupt"] is True, "Interrupt candidates should be preferred on tie"

    def test_cooldown_skipping(self):

        candidates = [
            {"kind": "warning", "salience": 0.9, "speaker_id": "npc:a", "target_id": "player", "reason": "hostile", "interrupt": True},
            {"kind": "gossip", "salience": 0.3, "speaker_id": "npc:b", "target_id": "", "reason": "idle", "interrupt": False},
        ]
        # npc:a on cooldown (spoke at tick 9, cooldown is 3 ticks)
        runtime = {
            "tick": 10,
            "ambient_cooldowns": {"speaker:npc:a": 9},
            "opening_runtime": {"active": False},
        }
        selected = select_npc_initiative_candidate(candidates, runtime)

        assert selected is not None
        assert selected["speaker_id"] == "npc:b", "Should skip NPC on cooldown"

    def test_returns_none_when_all_on_cooldown(self):

        candidates = [
            {"kind": "warning", "salience": 0.9, "speaker_id": "npc:a", "target_id": "player", "reason": "hostile", "interrupt": True},
        ]
        runtime = {
            "tick": 10,
            "ambient_cooldowns": {"speaker:npc:a": 10},
            "opening_runtime": {"active": False},
        }
        selected = select_npc_initiative_candidate(candidates, runtime)
        assert selected is None

    def test_returns_highest_priority(self):

        candidates = [
            {"kind": "gossip", "salience": 0.2, "speaker_id": "npc:x", "target_id": "", "reason": "chat", "interrupt": False},
            {"kind": "demand", "salience": 0.95, "speaker_id": "npc:y", "target_id": "player", "reason": "demand", "interrupt": True},
            {"kind": "taunt", "salience": 0.5, "speaker_id": "npc:z", "target_id": "player", "reason": "taunt", "interrupt": False},
        ]
        runtime = {"tick": 100, "ambient_cooldowns": {}, "opening_runtime": {"active": False}}
        selected = select_npc_initiative_candidate(candidates, runtime)

        assert selected is not None
        assert selected["salience"] == 0.95


# ════════════════════════════════════════════════════════════════════════════
# 3. Initiative Cooldowns
# ════════════════════════════════════════════════════════════════════════════


class TestInitiativeCooldowns:
    """Tests for apply_initiative_cooldowns()."""

    def test_all_cooldown_keys_recorded(self):

        runtime = {"tick": 10, "ambient_cooldowns": {}, "opening_runtime": {"active": False}}
        candidate = {
            "speaker_id": "npc:guard",
            "kind": "warning",
            "target_id": "player",
            "reason": "hostile_idle",
        }
        result = apply_initiative_cooldowns(runtime, candidate)

        cd = result["ambient_cooldowns"]
        assert "speaker:npc:guard" in cd
        assert "kind:warning" in cd
        assert "pair:npc:guard:player" in cd
        assert "reason:hostile_idle" in cd

    def test_existing_cooldowns_preserved(self):

        runtime = {
            "tick": 10,
            "ambient_cooldowns": {"speaker:npc:old": 5},
            "opening_runtime": {"active": False},
        }
        candidate = {
            "speaker_id": "npc:new",
            "kind": "gossip",
            "target_id": "",
            "reason": "idle",
        }
        result = apply_initiative_cooldowns(runtime, candidate)

        cd = result["ambient_cooldowns"]
        assert "speaker:npc:old" in cd
        assert cd["speaker:npc:old"] == 5
        assert "speaker:npc:new" in cd
        assert cd["speaker:npc:new"] == 10

    def test_opening_cooldown_recorded(self):

        runtime = {
            "tick": 10,
            "ambient_cooldowns": {},
            "opening_runtime": {
                "active": True,
                "present_npc_ids": ["npc:guard"],
                "starter_conflict": "thief_chase",
            },
        }
        candidate = {
            "speaker_id": "npc:guard",
            "kind": "warning",
            "target_id": "player",
            "reason": "opening_related",
        }
        result = apply_initiative_cooldowns(runtime, candidate)

        cd = result["ambient_cooldowns"]
        assert "opening:thief_chase" in cd


# ════════════════════════════════════════════════════════════════════════════
# 4. Opening Relevance
# ════════════════════════════════════════════════════════════════════════════


class TestOpeningRelevance:
    """Tests for compute_opening_relevance()."""

    def test_opening_npc_scores_higher(self):

        candidate = {"speaker_id": "npc:guard", "kind": "npc_to_player", "reason": "thief_chase_related"}
        opening = {
            "active": True,
            "present_npc_ids": ["npc:guard"],
            "starter_conflict": "thief_chase",
        }
        score = compute_opening_relevance(candidate, opening)
        # NPC tied (0.4) + starter_conflict in reason (0.3) + companion/npc_to_player (0.2) = 0.9
        assert score >= 0.4, "Opening NPC should score high"

    def test_non_opening_candidate_low_score(self):

        candidate = {"speaker_id": "npc:random", "kind": "gossip", "reason": "idle"}
        opening = {
            "active": True,
            "present_npc_ids": ["npc:guard"],
            "starter_conflict": "thief_chase",
        }
        score = compute_opening_relevance(candidate, opening)
        assert score == 0.0, "Non-opening NPC with no matching reason should score 0"

    def test_inactive_opening_scores_zero(self):

        candidate = {"speaker_id": "npc:guard", "kind": "warning", "reason": "hostile"}
        opening = {"active": False}
        score = compute_opening_relevance(candidate, opening)
        assert score == 0.0

    def test_companion_at_opening_gets_boost(self):

        candidate = {"speaker_id": "npc:ally", "kind": "companion_comment", "reason": "reaction"}
        opening = {
            "active": True,
            "present_npc_ids": ["npc:ally"],
            "starter_conflict": "rebellion",
        }
        score = compute_opening_relevance(candidate, opening)
        # NPC tied (0.4) + companion kind from opening NPC (0.2) = 0.6
        assert score >= 0.6


# ════════════════════════════════════════════════════════════════════════════
# 5. World Behavior Bias
# ════════════════════════════════════════════════════════════════════════════


class TestWorldBehaviorBias:
    """Tests for apply_world_behavior_bias()."""

    def test_low_npc_initiative_reduces_salience(self):

        candidates = [{"kind": "warning", "salience": 0.5}]
        result = apply_world_behavior_bias(candidates, {"npc_initiative": "low"})
        assert result[0]["salience"] < 0.5

    def test_high_npc_initiative_boosts_salience(self):

        candidates = [{"kind": "warning", "salience": 0.5}]
        result = apply_world_behavior_bias(candidates, {"npc_initiative": "high"})
        assert result[0]["salience"] > 0.5

    def test_quest_prompting_off_suppresses_quest_candidates(self):

        candidates = [{"kind": "quest_prompt", "salience": 0.6}]
        result = apply_world_behavior_bias(candidates, {"quest_prompting": "off"})
        # off applies -0.3, so 0.6 - 0.3 = 0.3
        assert result[0]["salience"] == pytest.approx(0.3, abs=0.01)

    def test_companion_chatter_quiet_reduces(self):

        candidates = [{"kind": "companion_comment", "salience": 0.5}]
        result = apply_world_behavior_bias(candidates, {"companion_chatter": "quiet"})
        # quiet applies -0.15, so 0.5 - 0.15 = 0.35
        assert result[0]["salience"] == pytest.approx(0.35, abs=0.01)

    def test_play_style_sandbox_boosts_incidental(self):

        candidates = [
            {"kind": "gossip", "salience": 0.3},
            {"kind": "quest_prompt", "salience": 0.6},
        ]
        result = apply_world_behavior_bias(candidates, {"play_style_bias": "sandbox"})
        gossip = [c for c in result if c["kind"] == "gossip"][0]
        quest = [c for c in result if c["kind"] == "quest_prompt"][0]
        assert gossip["salience"] > 0.3, "Sandbox should boost incidental"
        assert quest["salience"] < 0.6, "Sandbox should reduce steering"

    def test_play_style_story_directed_boosts_steering(self):

        candidates = [
            {"kind": "gossip", "salience": 0.3},
            {"kind": "quest_prompt", "salience": 0.6},
        ]
        result = apply_world_behavior_bias(candidates, {"play_style_bias": "story_directed"})
        gossip = [c for c in result if c["kind"] == "gossip"][0]
        quest = [c for c in result if c["kind"] == "quest_prompt"][0]
        assert gossip["salience"] < 0.3, "Story directed should reduce incidental"
        assert quest["salience"] > 0.6, "Story directed should boost steering"

    def test_empty_candidates_returns_empty(self):

        result = apply_world_behavior_bias([], {"npc_initiative": "high"})
        assert result == []

    def test_does_not_mutate_originals(self):

        original = {"kind": "warning", "salience": 0.5}
        apply_world_behavior_bias([original], {"npc_initiative": "low"})
        assert original["salience"] == 0.5, "Original should not be mutated"


# ════════════════════════════════════════════════════════════════════════════
# 6. World Event Director
# ════════════════════════════════════════════════════════════════════════════


class TestWorldEventDirector:
    """Tests for world_event_director functions."""

    def test_build_world_event_candidates_returns_events(self):

        sim = {
            "tick": 5,
            "factions": {
                "faction:rebels": {"name": "Rebels", "location_id": "loc:market", "pressure": 0.7},
            },
            "faction_pressure": {},
            "incidents": [],
            "npc_decisions": {},
            "npc_index": {},
            "resources": {},
            "environment": {},
            "events": [],
        }
        runtime = {}
        ctx = _player_context()
        candidates = build_world_event_candidates(sim, runtime, ctx)

        assert len(candidates) >= 1
        assert candidates[0]["event_type"] == "faction_movement"
        assert candidates[0]["visible_to_player"] is True

    def test_build_candidates_from_incidents(self):

        sim = {
            "tick": 5,
            "factions": {},
            "faction_pressure": {},
            "incidents": [
                {"incident_id": "inc1", "location_id": "loc:market", "type": "explosion", "severity": 0.8},
            ],
            "npc_decisions": {},
            "npc_index": {},
            "resources": {},
            "environment": {},
            "events": [],
        }
        candidates = build_world_event_candidates(sim, {}, _player_context())

        explosions = [c for c in candidates if c["event_type"] == "accident_explosion"]
        assert explosions, "Explosion incident should produce accident_explosion event"

    def test_filter_world_events_removes_low_priority(self):

        events = [
            {"kind": "world_event", "event_type": "weather_change", "priority": 0.1,
             "visible_to_player": True, "location_id": "loc:market"},
            {"kind": "world_event", "event_type": "faction_movement", "priority": 0.5,
             "visible_to_player": True, "location_id": "loc:market"},
        ]
        session = _minimal_session()
        result = filter_world_events(events, session)

        assert all(float(e.get("priority", 0)) >= 0.2 for e in result)
        assert len(result) == 1
        assert result[0]["event_type"] == "faction_movement"

    def test_filter_removes_invisible_events(self):

        events = [
            {"kind": "world_event", "event_type": "rumor_spread", "priority": 0.5,
             "visible_to_player": False, "location_id": "loc:market"},
        ]
        result = filter_world_events(events, _minimal_session())
        assert result == []

    def test_apply_world_behavior_to_events_harsh_boosts(self):

        events = [
            {"kind": "world_event", "event_type": "faction_movement", "priority": 0.5,
             "interrupt": False, "location_id": "loc:market"},
        ]
        wb = {"ambient_activity": "medium", "world_pressure": "harsh"}
        result = apply_world_behavior_to_events(events, wb)

        assert result[0]["priority"] > 0.5, "Harsh world pressure should boost priority"

    def test_apply_world_behavior_gentle_reduces(self):

        events = [
            {"kind": "world_event", "event_type": "faction_movement", "priority": 0.5,
             "interrupt": True, "location_id": "loc:market"},
        ]
        wb = {"ambient_activity": "medium", "world_pressure": "gentle"}
        result = apply_world_behavior_to_events(events, wb)

        assert result[0]["priority"] < 0.5, "Gentle world pressure should reduce priority"

    def test_apply_world_behavior_low_activity_filters(self):

        events = [
            {"kind": "world_event", "event_type": "weather_change", "priority": 0.35,
             "interrupt": False, "location_id": "loc:market"},
        ]
        wb = {"ambient_activity": "low", "world_pressure": "standard"}
        result = apply_world_behavior_to_events(events, wb)

        # threshold for "low" is 0.4, priority is 0.35 → filtered
        assert result == [], "Low activity threshold should filter events below 0.4"

    def test_convert_events_to_ambient_updates_structure(self):

        events = [
            {"kind": "world_event", "event_type": "faction_movement", "priority": 0.5,
             "interrupt": False, "text": "The rebels are moving.", "tick": 5,
             "location_id": "loc:market", "faction_id": "faction:rebels",
             "source": "world_director"},
        ]
        runtime = {"ambient_seq": 0}
        updates = convert_events_to_ambient_updates(events, runtime)

        assert len(updates) == 1
        u = updates[0]
        assert u["kind"] == "world_event"
        assert u["text"] == "The rebels are moving."
        assert u["priority"] == 0.5
        assert u["structured"]["event_type"] == "faction_movement"
        assert u["structured"]["faction_id"] == "faction:rebels"
        assert u["created_at"]  # Non-empty timestamp

    def test_max_events_per_tick_cap(self):
        events = [
            {"kind": "world_event", "event_type": f"type_{i}", "priority": 0.5,
             "interrupt": False, "text": f"Event {i}", "tick": 5,
             "location_id": "loc:market", "source": "test"}
            for i in range(10)
        ]
        updates = convert_events_to_ambient_updates(events, {"ambient_seq": 0})
        assert len(updates) <= MAX_WORLD_EVENTS_PER_TICK


# ════════════════════════════════════════════════════════════════════════════
# 7. World Behavior Config
# ════════════════════════════════════════════════════════════════════════════


class TestWorldBehaviorConfig:
    """Tests for schema/defaults/validation."""

    def test_normalize_fills_defaults(self):

        result = normalize_world_behavior_config(None)
        assert result["ambient_activity"] == "medium"
        assert result["npc_initiative"] == "medium"
        assert result["quest_prompting"] == "guided"
        assert result["world_pressure"] == "standard"

    def test_normalize_rejects_invalid_values(self):

        result = normalize_world_behavior_config({"npc_initiative": "INVALID", "quest_prompting": "extreme"})
        assert result["npc_initiative"] == "medium", "Invalid value should fall back to default"
        assert result["quest_prompting"] == "guided", "Invalid value should fall back to default"

    def test_normalize_accepts_valid_values(self):

        result = normalize_world_behavior_config({
            "ambient_activity": "high",
            "npc_initiative": "low",
            "quest_prompting": "off",
            "world_pressure": "harsh",
        })
        assert result["ambient_activity"] == "high"
        assert result["npc_initiative"] == "low"
        assert result["quest_prompting"] == "off"
        assert result["world_pressure"] == "harsh"

    def test_from_dict_to_dict_roundtrip(self):

        original = {"ambient_activity": "high", "npc_initiative": "low", "world_pressure": "harsh"}
        config = WorldBehaviorConfig.from_dict(original)
        d = config.to_dict()
        config2 = WorldBehaviorConfig.from_dict(d)
        assert config.to_dict() == config2.to_dict()

    def test_from_dict_normalizes(self):

        config = WorldBehaviorConfig.from_dict({"npc_initiative": "BOGUS"})
        assert config.npc_initiative == "medium", "from_dict should normalize invalid values"

    def test_genre_specific_defaults_differ(self):

        fantasy = infer_default_world_behavior({"genre": "fantasy"})
        grimdark = infer_default_world_behavior({"genre": "grimdark"})

        assert fantasy != grimdark, "Genre defaults should differ"
        assert grimdark["world_pressure"] == "harsh"
        assert fantasy["world_pressure"] == "standard"

    def test_validate_world_behavior_catches_invalid(self):

        payload = {
            "world_behavior": {"npc_initiative": "turbo", "quest_prompting": "ultra"},
        }
        issues = validate_world_behavior(payload)
        assert len(issues) >= 2
        codes = [i.code for i in issues]
        assert "invalid_world_behavior_value" in codes

    def test_validate_world_behavior_detects_contradictions(self):

        payload = {
            "world_behavior": {
                "play_style_bias": "sandbox",
                "opening_guidance": "strong",
            },
        }
        issues = validate_world_behavior(payload)
        contrad = [i for i in issues if i.code == "contradictory_world_behavior"]
        assert contrad, "Sandbox + strong opening guidance should be flagged"


# ════════════════════════════════════════════════════════════════════════════
# 8. Ambient Policy Quiet Window
# ════════════════════════════════════════════════════════════════════════════


class TestAmbientPolicyQuietWindow:
    """Tests for updated ambient_policy."""

    def test_quiet_window_suppresses_interrupts(self):

        session = _minimal_session()
        session["runtime_state"]["post_player_quiet_ticks"] = 3
        update = {"kind": "npc_to_player", "priority": 0.7, "target_id": "player"}

        assert should_interrupt_player(session, update) is False

    def test_urgent_events_break_quiet_window(self):

        session = _minimal_session()
        session["runtime_state"]["post_player_quiet_ticks"] = 3
        update = {"kind": "combat_start", "priority": 0.95, "target_id": "player"}

        assert should_interrupt_player(session, update) is True

    def test_quest_prompt_classified_interrupt(self):

        session = _minimal_session()
        update = {"kind": "quest_prompt", "priority": 0.8, "target_id": "player"}

        assert should_interrupt_player(session, update) is True

    def test_plea_for_help_classified_interrupt(self):

        session = _minimal_session()
        update = {"kind": "plea_for_help", "priority": 0.7, "target_id": "player"}

        assert should_interrupt_player(session, update) is True

    def test_demand_classified_interrupt(self):

        session = _minimal_session()
        update = {"kind": "demand", "priority": 0.7, "target_id": "player"}

        assert should_interrupt_player(session, update) is True

    def test_gossip_not_interrupt(self):

        session = _minimal_session()
        update = {"kind": "gossip", "priority": 0.5, "target_id": ""}

        assert should_interrupt_player(session, update) is False

    def test_classify_delivery_interrupt(self):

        session = _minimal_session()
        update = {"kind": "combat_start", "priority": 0.95, "target_id": "player"}

        assert classify_ambient_delivery(session, update) == "interrupt"

    def test_classify_delivery_badge_medium_priority(self):

        session = _minimal_session()
        update = {"kind": "world_event", "priority": 0.45, "target_id": ""}

        assert classify_ambient_delivery(session, update) == "badge"

    def test_classify_delivery_silent_low_priority(self):

        session = _minimal_session()
        update = {"kind": "world_event", "priority": 0.15, "target_id": ""}

        assert classify_ambient_delivery(session, update) == "silent"


# ════════════════════════════════════════════════════════════════════════════
# 9. Runtime Integration
# ════════════════════════════════════════════════════════════════════════════


class TestRuntimeIntegration:
    """Tests for runtime helpers."""

    def test_compute_idle_tick_encounter_suppression(self):

        session = _minimal_session()
        session["simulation_state"]["encounter_active"] = True

        result = compute_idle_tick_count(session, reason="heartbeat")
        assert result == 0, "Active encounter should suppress idle ticks"

    def test_compute_idle_tick_quiet_window_suppression(self):

        session = _minimal_session()
        session["runtime_state"]["post_player_quiet_ticks"] = 2

        result = compute_idle_tick_count(session, reason="heartbeat")
        assert result == 0, "Quiet window should suppress idle ticks"

    def test_compute_idle_tick_normal_heartbeat(self):

        session = _minimal_session()
        result = compute_idle_tick_count(session, reason="heartbeat")
        assert result == 1

    def test_compute_idle_tick_resume_catchup(self):

        session = _minimal_session()
        result = compute_idle_tick_count(session, elapsed_seconds=60, reason="resume_catchup")
        assert result > 0
        assert result <= 12  # _MAX_RESUME_CATCHUP_TICKS

    def test_build_opening_runtime_creates_correct_structure(self):

        setup = {
            "opening": {
                "scene_frame": "A burning village",
                "immediate_problem": "Raiders attack",
                "player_involvement_reason": "Home destroyed",
                "present_npc_ids": ["npc:elder", "npc:guard"],
                "first_choices": ["fight", "flee"],
                "location_id": "loc:village",
            },
            "starter_conflict": "raider_attack",
        }
        result = _build_opening_runtime(setup)

        assert result["active"] is True
        assert result["scene_frame"] == "A burning village"
        assert result["immediate_problem"] == "Raiders attack"
        assert result["present_npc_ids"] == ["npc:elder", "npc:guard"]
        assert result["starter_conflict"] == "raider_attack"
        assert result["opening_resolved"] is False

    def test_build_opening_runtime_no_opening(self):

        result = _build_opening_runtime({})
        assert result["active"] is False
        assert result["opening_resolved"] is True

    def test_check_opening_resolution_after_tick_threshold(self):

        session = _minimal_session(tick=12)
        session["simulation_state"]["tick"] = 12

        result = _check_opening_resolution(session)
        assert result["opening_resolved"] is True
        assert result["active"] is False

    def test_check_opening_resolution_inactive_passthrough(self):

        session = _minimal_session()
        session["runtime_state"]["opening_runtime"] = {"active": False, "opening_resolved": True}
        result = _check_opening_resolution(session)
        assert result["opening_resolved"] is True

    def test_get_effective_world_behavior_merges_override(self):

        session = _minimal_session()
        session["setup_payload"]["world_behavior"] = {
            "npc_initiative": "medium",
            "quest_prompting": "guided",
        }
        session["runtime_state"]["world_behavior_override"] = {
            "npc_initiative": "high",
        }
        result = get_effective_world_behavior(session)

        assert result["npc_initiative"] == "high", "Override should win"
        assert result["quest_prompting"] == "guided", "Non-overridden should remain"

    def test_get_effective_world_behavior_invalid_override_ignored(self):

        session = _minimal_session()
        session["setup_payload"]["world_behavior"] = {"npc_initiative": "medium"}
        session["runtime_state"]["world_behavior_override"] = {"npc_initiative": "BOGUS"}
        result = get_effective_world_behavior(session)
        assert result["npc_initiative"] == "medium", "Invalid override should be ignored"

    def test_make_initiative_update_from_candidate_structure(self):

        candidate = {
            "kind": "quest_prompt",
            "speaker_id": "npc:elder",
            "speaker_name": "Elder",
            "target_id": "player",
            "target_name": "you",
            "salience": 0.7,
            "interrupt": False,
            "reason": "objective_related",
            "action_intent": "offer_quest",
            "location_id": "loc:market",
            "tick": 5,
        }
        update = _make_initiative_update_from_candidate(candidate)

        assert update["kind"] == "quest_prompt"
        assert update["speaker_id"] == "npc:elder"
        assert update["priority"] == 0.7
        assert update["source"] == "initiative"
        assert "quest" in update["text"].lower()
        assert update["structured"]["reason"] == "objective_related"
        assert update["structured"]["action_intent"] == "offer_quest"

    def test_make_initiative_update_default_text_for_kinds(self):

        for kind, keyword in [
            ("taunt", "confronts"),
            ("warning", "warns"),
            ("companion_comment", "something to say"),
            ("plea_for_help", "help"),
            ("recruitment_offer", "offer"),
        ]:
            update = _make_initiative_update_from_candidate({
                "kind": kind, "speaker_name": "NPC", "speaker_id": "npc:x",
                "target_id": "player", "salience": 0.5, "tick": 1,
            })
            assert keyword in update["text"].lower(), f"Kind '{kind}' should contain '{keyword}' in text"


# ════════════════════════════════════════════════════════════════════════════
# 10. Ambient Builder Extensions
# ════════════════════════════════════════════════════════════════════════════


class TestAmbientBuilderExtensions:
    """Tests for ambient_builder changes supporting new kinds."""

    def test_new_kinds_visible_to_player(self):

        session = _minimal_session()
        for kind in ("quest_prompt", "plea_for_help", "demand", "taunt", "recruitment_offer"):
            update = {"kind": kind, "target_id": "player", "priority": 0.5, "location_id": "loc:market"}
            assert is_player_visible_update(update, session), f"{kind} targeting player should be visible"

    def test_invisible_if_different_location(self):

        session = _minimal_session()
        update = {"kind": "gossip", "target_id": "", "priority": 0.3, "location_id": "loc:faraway"}
        assert is_player_visible_update(update, session) is False

    def test_salience_scoring_for_new_kinds(self):

        context = {"player_location": "loc:market", "nearby_npc_ids": [], "recent_ambient_ids": []}

        quest = score_ambient_salience({"kind": "quest_prompt", "priority": 0.5}, context)
        gossip = score_ambient_salience({"kind": "gossip", "priority": 0.5}, context)

        assert quest > gossip, "quest_prompt should score higher than gossip"

    def test_salience_scoring_taunt_high(self):

        context = {"player_location": "loc:market", "nearby_npc_ids": [], "recent_ambient_ids": []}
        taunt = score_ambient_salience({"kind": "taunt", "priority": 0.5}, context)
        assert taunt >= 0.9, "Taunt should have high salience bonus"

    def test_salience_scoring_plea_for_help(self):

        context = {"player_location": "loc:market", "nearby_npc_ids": [], "recent_ambient_ids": []}
        plea = score_ambient_salience({"kind": "plea_for_help", "priority": 0.5}, context)
        demand = score_ambient_salience({"kind": "demand", "priority": 0.5}, context)
        assert plea > 0.5
        assert demand > 0.5

    def test_coalescing_high_priority_kinds_preserved(self):

        updates = [
            {"kind": "quest_prompt", "priority": 0.7, "text": "Quest info", "speaker_id": "npc:a"},
            {"kind": "plea_for_help", "priority": 0.6, "text": "Help needed", "speaker_id": "npc:b"},
            {"kind": "demand", "priority": 0.8, "text": "Demand made", "speaker_id": "npc:c"},
        ]
        runtime = {"ambient_metrics": {"coalesced": 0}}
        result = coalesce_ambient_updates(updates, runtime)

        # All three should be in high_priority and preserved
        kinds = [u["kind"] for u in result]
        assert "quest_prompt" in kinds
        assert "plea_for_help" in kinds
        assert "demand" in kinds

    def test_coalescing_npc_chatter_capped(self):

        updates = [
            {"kind": "companion_comment", "priority": 0.4, "text": f"Comment {i}", "speaker_id": f"npc:{i}"}
            for i in range(5)
        ]
        runtime = {"ambient_metrics": {"coalesced": 0}}
        result = coalesce_ambient_updates(updates, runtime)

        chatter = [u for u in result if u["kind"] == "companion_comment"]
        assert len(chatter) <= 2, "NPC chatter should be capped at 2"

    def test_coalescing_taunt_in_npc_chatter_group(self):

        updates = [
            {"kind": "taunt", "priority": 0.7, "text": "Threat 1", "speaker_id": "npc:a"},
            {"kind": "gossip", "priority": 0.2, "text": "Gossip 1", "speaker_id": "npc:b"},
            {"kind": "gossip", "priority": 0.2, "text": "Gossip 2", "speaker_id": "npc:c"},
            {"kind": "gossip", "priority": 0.2, "text": "Gossip 3", "speaker_id": "npc:d"},
        ]
        runtime = {"ambient_metrics": {"coalesced": 0}}
        result = coalesce_ambient_updates(updates, runtime)

        # Taunt and gossip are in npc_chatter group, capped to 2
        chatter_kinds = [u["kind"] for u in result if u["kind"] in ("taunt", "gossip")]
        assert len(chatter_kinds) <= 2
