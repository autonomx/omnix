"""Phase 8.3 — World Simulation Unit Tests.

Covers pure logic: models roundtrip, reducer determinism, controller
lifecycle, presenter output, journal builder, memory core recording,
coherence/social query helpers, arc guidance, encounter seeding, and UX
model integration.
"""

from __future__ import annotations

import copy
import os
import sys

# Ensure src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from app.rpg.world_sim.models import (
    SUPPORTED_LOCATION_CONDITIONS,
    SUPPORTED_WORLD_EFFECT_TYPES,
    SUPPORTED_WORLD_SIM_STATUSES,
    FactionDriftState,
    LocationConditionState,
    NPCActivityState,
    RumorPropagationState,
    WorldEffect,
    WorldPressureState,
    WorldSimState,
    WorldSimTickResult,
)
from app.rpg.world_sim.controller import WorldSimController
from app.rpg.world_sim.presenter import WorldSimPresenter
from app.rpg.world_sim.reducers import (
    build_world_sim_trace,
    reduce_faction_drift,
    reduce_location_conditions,
    reduce_npc_activities,
    reduce_rumor_propagation,
    reduce_world_pressure,
)
from app.rpg.memory.journal_builder import JournalBuilder
from app.rpg.memory.core import CampaignMemoryCore
from app.rpg.encounter.controller import EncounterController
from app.rpg.ux.models import ActionResultPayload, SceneUXPayload


# ======================================================================
# Helpers — shared fixture builders
# ======================================================================

def _make_seed_context(**overrides) -> dict:
    """Build a minimal seed context dict with sane defaults."""
    ctx = {
        "tick": 1,
        "known_factions": ["guild_a", "guild_b"],
        "known_locations": ["market", "docks", "tavern"],
        "unresolved_threads": [],
        "recent_consequences": [],
        "scene_entities": ["player", "guard_a", "merchant_b"],
        "active_scene_location": "market",
        "recent_rumors": [],
        "faction_pressure_map": {},
        "arc_guidance": {},
        "encounter_aftermath": {},
    }
    ctx.update(overrides)
    return ctx


def _make_faction_drift(faction_id: str = "guild_a", **kw) -> dict:
    return FactionDriftState(faction_id=faction_id, **kw).to_dict()


def _make_rumor_state(rumor_id: str = "rumor_1", **kw) -> dict:
    return RumorPropagationState(rumor_id=rumor_id, **kw).to_dict()


def _make_location_condition(location_id: str = "market", **kw) -> dict:
    return LocationConditionState(location_id=location_id, **kw).to_dict()


def _make_npc_activity(entity_id: str = "guard_a", **kw) -> dict:
    return NPCActivityState(entity_id=entity_id, **kw).to_dict()


def _make_world_effect(
    effect_id: str = "eff-1",
    effect_type: str = "faction_shift",
    scope: str = "faction",
    **kw,
) -> dict:
    return WorldEffect(
        effect_id=effect_id, effect_type=effect_type, scope=scope, **kw
    ).to_dict()


class _MockCoherenceQuery:
    """Minimal mock implementing coherence query interface."""

    def __init__(
        self,
        locations: list[str] | None = None,
        scene_location: str | None = "market",
        threads: list[dict] | None = None,
        consequences: list[dict] | None = None,
        entities: list[str] | None = None,
    ):
        self._locations = locations or ["market", "docks"]
        self._scene_location = scene_location
        self._threads = threads or []
        self._consequences = consequences or []
        self._entities = entities or ["player", "guard_a"]

    def get_known_locations(self) -> list[str]:
        return list(self._locations)

    def get_active_scene_location(self) -> str | None:
        return self._scene_location

    def get_scene_summary(self) -> dict:
        return {"location": self._scene_location, "summary": "A scene."}

    def get_unresolved_threads(self) -> list[dict]:
        return list(self._threads)

    def get_recent_consequences(self, limit: int = 5) -> list[dict]:
        return list(self._consequences[:limit])

    def get_scene_entities(self) -> list[str]:
        return list(self._entities)

    def get_active_threads(self) -> list[dict]:
        return list(self._threads)

    def get_location_facts(self, location_id: str | None = None) -> dict:
        return {"location_id": location_id, "facts": []}


class _MockCoherenceCore:
    """Minimal mock of coherence core with a query attribute."""

    def __init__(self, **kw):
        self.query = _MockCoherenceQuery(**kw)


class _MockSocialState:
    """Minimal mock of social state model."""

    def __init__(self, alliances=None, rumors=None, relationships=None):
        self.alliances = alliances or {}
        self.rumors = rumors or {}
        self.relationships = relationships or {}


class _MockAlliance:
    def __init__(self, entity_a: str, entity_b: str):
        self.entity_a = entity_a
        self.entity_b = entity_b


class _MockRumor:
    def __init__(self, rumor_id: str, active: bool = True, **kw):
        self.rumor_id = rumor_id
        self.active = active
        self.source_npc_id = kw.get("source_npc_id", "npc_a")
        self.subject_id = kw.get("subject_id", "subject_b")
        self.summary = kw.get("summary", "A juicy rumor.")
        self.location = kw.get("location", "tavern")

    def to_dict(self) -> dict:
        return {
            "rumor_id": self.rumor_id,
            "active": self.active,
            "source_npc_id": self.source_npc_id,
            "subject_id": self.subject_id,
            "summary": self.summary,
            "location": self.location,
        }


class _MockRelationship:
    def __init__(self, source_id: str, target_id: str, status: str = "neutral"):
        self.source_id = source_id
        self.target_id = target_id
        self.status = status


class _MockSocialStateCore:
    """Minimal mock of social state core."""

    def __init__(self, state: _MockSocialState | None = None):
        self._state = state or _MockSocialState()

    def get_state(self) -> _MockSocialState:
        return self._state

    def get_query(self):
        return self  # returns non-None so query branch runs


class _MockArcControlController:
    """Minimal mock of arc control controller."""

    def __init__(self, guidance: dict | None = None):
        self._guidance = guidance or {
            "top_active_arcs": [],
            "reveal_pressure": "normal",
            "pacing_pressure": "normal",
            "escalation_bias": "neutral",
            "preferred_thread_pressure_targets": [],
        }

    def build_world_sim_guidance(self) -> dict:
        return dict(self._guidance)


# ======================================================================
# Model tests — Serialization roundtrips
# ======================================================================


def test_world_effect_roundtrip():
    obj = WorldEffect(
        effect_id="e1", effect_type="faction_shift", scope="faction",
        target_id="guild_a", payload={"key": "val"}, journalable=True,
        metadata={"m": 1},
    )
    d = obj.to_dict()
    restored = WorldEffect.from_dict(d)
    assert restored.to_dict() == d


def test_world_effect_defaults():
    obj = WorldEffect.from_dict({})
    assert obj.effect_id == ""
    assert obj.effect_type == ""
    assert obj.scope == ""
    assert obj.target_id is None
    assert obj.payload == {}
    assert obj.journalable is False
    assert obj.metadata == {}


def test_faction_drift_state_roundtrip():
    obj = FactionDriftState(
        faction_id="guild_a", momentum="assertive", pressure="high",
        stance_overrides={"x": "y"}, active_goals=["g1"],
        recent_changes=[{"c": 1}], metadata={"m": 1},
    )
    d = obj.to_dict()
    restored = FactionDriftState.from_dict(d)
    assert restored.to_dict() == d


def test_faction_drift_state_defaults():
    obj = FactionDriftState.from_dict({"faction_id": "f"})
    assert obj.momentum == "steady"
    assert obj.pressure == "low"
    assert obj.stance_overrides == {}
    assert obj.active_goals == []
    assert obj.recent_changes == []


def test_rumor_propagation_state_roundtrip():
    obj = RumorPropagationState(
        rumor_id="r1", source_entity_id="npc_a",
        subject_entity_id="npc_b", origin_location="tavern",
        current_locations=["tavern", "market"], reach=2, heat="warm",
        status="active", metadata={"m": 1},
    )
    d = obj.to_dict()
    restored = RumorPropagationState.from_dict(d)
    assert restored.to_dict() == d


def test_rumor_propagation_state_defaults():
    obj = RumorPropagationState.from_dict({"rumor_id": "r"})
    assert obj.source_entity_id is None
    assert obj.subject_entity_id is None
    assert obj.origin_location is None
    assert obj.current_locations == []
    assert obj.reach == 0
    assert obj.heat == "cold"
    assert obj.status == "dormant"


def test_location_condition_state_roundtrip():
    obj = LocationConditionState(
        location_id="market", conditions=["tense", "guarded"],
        pressure="high", activity_level="elevated",
        active_flags=["patrol"], metadata={"m": 1},
    )
    d = obj.to_dict()
    restored = LocationConditionState.from_dict(d)
    assert restored.to_dict() == d


def test_location_condition_state_defaults():
    obj = LocationConditionState.from_dict({"location_id": "loc"})
    assert obj.conditions == []
    assert obj.pressure == "low"
    assert obj.activity_level == "normal"
    assert obj.active_flags == []


def test_npc_activity_state_roundtrip():
    obj = NPCActivityState(
        entity_id="guard_a", current_location="market",
        activity="patrolling", visibility="visible", status="alert",
        last_update_tick=5, metadata={"m": 1},
    )
    d = obj.to_dict()
    restored = NPCActivityState.from_dict(d)
    assert restored.to_dict() == d


def test_npc_activity_state_defaults():
    obj = NPCActivityState.from_dict({"entity_id": "npc"})
    assert obj.current_location is None
    assert obj.activity == "idle"
    assert obj.visibility == "unknown"
    assert obj.status == "normal"
    assert obj.last_update_tick is None


def test_world_pressure_state_roundtrip():
    obj = WorldPressureState(
        active_threads=["t1", "t2"],
        pressure_by_thread={"t1": "medium"},
        pressure_by_location={"market": "high"},
        pressure_by_faction={"guild_a": "low"},
        metadata={"m": 1},
    )
    d = obj.to_dict()
    restored = WorldPressureState.from_dict(d)
    assert restored.to_dict() == d


def test_world_pressure_state_defaults():
    obj = WorldPressureState.from_dict({})
    assert obj.active_threads == []
    assert obj.pressure_by_thread == {}
    assert obj.pressure_by_location == {}
    assert obj.pressure_by_faction == {}


def test_world_sim_state_roundtrip():
    state = WorldSimState(
        sim_tick=3, status="active",
        faction_drift={"guild_a": FactionDriftState(faction_id="guild_a")},
        rumor_states={"r1": RumorPropagationState(rumor_id="r1")},
        location_conditions={"market": LocationConditionState(location_id="market")},
        npc_activities={"guard_a": NPCActivityState(entity_id="guard_a")},
        world_pressure=WorldPressureState(active_threads=["t1"]),
        recent_effects=[{"effect_type": "faction_shift"}],
        last_result={"tick": 3},
        metadata={"m": 1},
    )
    d = state.to_dict()
    restored = WorldSimState.from_dict(d)
    assert restored.to_dict() == d


def test_world_sim_state_defaults():
    state = WorldSimState.from_dict({})
    assert state.sim_tick == 0
    assert state.status == "idle"
    assert state.faction_drift == {}
    assert state.rumor_states == {}
    assert state.location_conditions == {}
    assert state.npc_activities == {}
    assert state.recent_effects == []
    assert state.last_result == {}


def test_world_sim_tick_result_roundtrip():
    result = WorldSimTickResult(
        tick=5, advanced=True,
        generated_effects=[{"effect_type": "rumor_spread"}],
        generated_summaries=[{"summary_type": "world_sim_tick"}],
        journal_payloads=[{"journalable": True}],
        trace={"tick": 5}, metadata={"m": 1},
    )
    d = result.to_dict()
    restored = WorldSimTickResult.from_dict(d)
    assert restored.to_dict() == d


def test_world_sim_tick_result_defaults():
    result = WorldSimTickResult.from_dict({})
    assert result.tick is None
    assert result.advanced is False
    assert result.generated_effects == []
    assert result.generated_summaries == []
    assert result.journal_payloads == []
    assert result.trace == {}


def test_world_sim_state_to_dict_returns_copy():
    state = WorldSimState(recent_effects=[{"a": 1}])
    d1 = state.to_dict()
    d2 = state.to_dict()
    d1["recent_effects"].append({"b": 2})
    assert len(d2["recent_effects"]) == 1


# ======================================================================
# Constants tests
# ======================================================================


def test_supported_effect_types_is_frozenset():
    assert isinstance(SUPPORTED_WORLD_EFFECT_TYPES, frozenset)


def test_supported_effect_types_contains_faction_shift():
    assert "faction_shift" in SUPPORTED_WORLD_EFFECT_TYPES


def test_supported_effect_types_contains_rumor_spread():
    assert "rumor_spread" in SUPPORTED_WORLD_EFFECT_TYPES


def test_supported_effect_types_contains_location_condition_changed():
    assert "location_condition_changed" in SUPPORTED_WORLD_EFFECT_TYPES


def test_supported_effect_types_contains_npc_activity_changed():
    assert "npc_activity_changed" in SUPPORTED_WORLD_EFFECT_TYPES


def test_supported_effect_types_contains_thread_pressure_changed():
    assert "thread_pressure_changed" in SUPPORTED_WORLD_EFFECT_TYPES


def test_supported_effect_types_contains_encounter_seeded():
    assert "encounter_seeded" in SUPPORTED_WORLD_EFFECT_TYPES


def test_supported_location_conditions_is_frozenset():
    assert isinstance(SUPPORTED_LOCATION_CONDITIONS, frozenset)


def test_supported_location_conditions_contains_guarded():
    assert "guarded" in SUPPORTED_LOCATION_CONDITIONS


def test_supported_location_conditions_contains_tense():
    assert "tense" in SUPPORTED_LOCATION_CONDITIONS


def test_supported_location_conditions_contains_calm():
    assert "calm" in SUPPORTED_LOCATION_CONDITIONS


def test_supported_statuses_is_frozenset():
    assert isinstance(SUPPORTED_WORLD_SIM_STATUSES, frozenset)


def test_supported_statuses_contains_idle():
    assert "idle" in SUPPORTED_WORLD_SIM_STATUSES


def test_supported_statuses_contains_active():
    assert "active" in SUPPORTED_WORLD_SIM_STATUSES


def test_supported_statuses_contains_paused():
    assert "paused" in SUPPORTED_WORLD_SIM_STATUSES


# ======================================================================
# Reducer tests — faction drift
# ======================================================================


def test_reduce_faction_drift_deterministic():
    current = {"guild_a": _make_faction_drift("guild_a")}
    ctx = _make_seed_context()
    r1 = reduce_faction_drift(dict(current), dict(ctx))
    r2 = reduce_faction_drift(dict(current), dict(ctx))
    assert r1[0] == r2[0]
    assert r1[1] == r2[1]


def test_reduce_faction_drift_unresolved_threads_raise_pressure():
    threads = [
        {"thread_id": "guild_a_theft"},
        {"thread_id": "guild_a_raid"},
    ]
    ctx = _make_seed_context(unresolved_threads=threads)
    current = {"guild_a": _make_faction_drift("guild_a", pressure="low")}
    updated, effects = reduce_faction_drift(current, ctx)
    assert updated["guild_a"]["pressure"] in ("medium", "high", "critical")


def test_reduce_faction_drift_no_threads_deescalate():
    ctx = _make_seed_context(
        unresolved_threads=[],
        faction_pressure_map={},
    )
    current = {"guild_a": _make_faction_drift("guild_a", pressure="medium")}
    updated, _ = reduce_faction_drift(current, ctx)
    assert updated["guild_a"]["pressure"] == "low"


def test_reduce_faction_drift_consequences_cause_defensive():
    # Need threads mentioning the faction to prevent the no-threads branch
    # from resetting momentum back to steady after consequences set it.
    consequences = [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}]
    threads = [{"thread_id": "guild_a_plot"}]
    ctx = _make_seed_context(
        recent_consequences=consequences,
        unresolved_threads=threads,
    )
    current = {"guild_a": _make_faction_drift("guild_a", momentum="steady")}
    updated, _ = reduce_faction_drift(current, ctx)
    assert updated["guild_a"]["momentum"] == "defensive"


def test_reduce_faction_drift_effects_have_correct_type():
    threads = [
        {"thread_id": "guild_a_theft"},
        {"thread_id": "guild_a_raid"},
    ]
    ctx = _make_seed_context(unresolved_threads=threads)
    current = {"guild_a": _make_faction_drift("guild_a")}
    _, effects = reduce_faction_drift(current, ctx)
    for eff in effects:
        assert eff["effect_type"] in SUPPORTED_WORLD_EFFECT_TYPES


def test_reduce_faction_drift_empty_input():
    ctx = _make_seed_context(known_factions=[])
    updated, effects = reduce_faction_drift({}, ctx)
    assert updated == {}
    assert effects == []


def test_reduce_faction_drift_external_pressure_map_applied():
    ctx = _make_seed_context(faction_pressure_map={"guild_a": "high"})
    current = {"guild_a": _make_faction_drift("guild_a", pressure="low")}
    updated, _ = reduce_faction_drift(current, ctx)
    assert updated["guild_a"]["pressure"] == "high"


def test_reduce_faction_drift_assertive_to_steady_on_consequences():
    consequences = [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}]
    ctx = _make_seed_context(recent_consequences=consequences)
    current = {"guild_a": _make_faction_drift("guild_a", momentum="assertive")}
    updated, _ = reduce_faction_drift(current, ctx)
    assert updated["guild_a"]["momentum"] == "steady"


# ======================================================================
# Reducer tests — rumor propagation
# ======================================================================


def test_reduce_rumor_propagation_deterministic():
    current = {"r1": _make_rumor_state("r1", heat="warm", status="active",
                                        current_locations=["tavern"])}
    ctx = _make_seed_context()
    r1 = reduce_rumor_propagation(dict(current), dict(ctx))
    r2 = reduce_rumor_propagation(dict(current), dict(ctx))
    assert r1[0] == r2[0]
    assert r1[1] == r2[1]


def test_reduce_rumor_propagation_seeds_from_social_state():
    ctx = _make_seed_context(recent_rumors=[
        {"rumor_id": "new_r", "source_npc_id": "npc_a",
         "subject_id": "npc_b", "location": "tavern"},
    ])
    updated, effects = reduce_rumor_propagation({}, ctx)
    assert "new_r" in updated
    assert updated["new_r"]["status"] == "active" or updated["new_r"]["heat"] in ("warm", "cold")


def test_reduce_rumor_propagation_warm_rumors_spread():
    current = {"r1": _make_rumor_state(
        "r1", heat="warm", status="active",
        current_locations=["tavern"], reach=1,
    )}
    ctx = _make_seed_context(known_locations=["tavern", "market", "docks"])
    updated, effects = reduce_rumor_propagation(current, ctx)
    # Should spread to at least one new location
    spread_effects = [e for e in effects if e["effect_type"] == "rumor_spread"]
    assert len(spread_effects) >= 1
    assert len(updated["r1"]["current_locations"]) > 1


def test_reduce_rumor_propagation_cold_rumors_dont_spread():
    current = {"r1": _make_rumor_state(
        "r1", heat="cold", status="dormant",
        current_locations=["tavern"], reach=1,
    )}
    ctx = _make_seed_context(known_locations=["tavern", "market"])
    updated, effects = reduce_rumor_propagation(current, ctx)
    spread_effects = [e for e in effects if e["effect_type"] == "rumor_spread"]
    assert len(spread_effects) == 0
    assert len(updated["r1"]["current_locations"]) == 1


def test_reduce_rumor_propagation_high_reach_cools_down():
    current = {"r1": _make_rumor_state(
        "r1", heat="warm", status="active",
        current_locations=["a", "b", "c", "d", "e"], reach=5,
    )}
    ctx = _make_seed_context(known_locations=["a", "b", "c", "d", "e"])
    updated, _ = reduce_rumor_propagation(current, ctx)
    # Warm + reach >= 5 → cools to cold/dormant
    assert updated["r1"]["heat"] == "cold"
    assert updated["r1"]["status"] == "dormant"


def test_reduce_rumor_propagation_effects_have_correct_types():
    current = {"r1": _make_rumor_state(
        "r1", heat="warm", status="active",
        current_locations=["tavern"], reach=1,
    )}
    ctx = _make_seed_context()
    _, effects = reduce_rumor_propagation(current, ctx)
    for eff in effects:
        assert eff["effect_type"] in SUPPORTED_WORLD_EFFECT_TYPES


def test_reduce_rumor_propagation_empty_input():
    ctx = _make_seed_context(recent_rumors=[])
    updated, effects = reduce_rumor_propagation({}, ctx)
    assert updated == {}
    assert effects == []


# ======================================================================
# Reducer tests — location conditions
# ======================================================================


def test_reduce_location_conditions_deterministic():
    current = {"market": _make_location_condition("market")}
    ctx = _make_seed_context()
    r1 = reduce_location_conditions(dict(current), dict(ctx))
    r2 = reduce_location_conditions(dict(current), dict(ctx))
    assert r1[0] == r2[0]
    assert r1[1] == r2[1]


def test_reduce_location_conditions_consequences_add_tense():
    consequences = [{"id": "c1"}, {"id": "c2"}]
    ctx = _make_seed_context(recent_consequences=consequences)
    current = {"market": _make_location_condition("market", conditions=[])}
    updated, _ = reduce_location_conditions(current, ctx)
    assert "tense" in updated["market"]["conditions"]


def test_reduce_location_conditions_encounter_aftermath_adds_guarded():
    ctx = _make_seed_context(
        encounter_aftermath={"mode": "combat", "location": "market"},
        active_scene_location="market",
    )
    current = {"market": _make_location_condition("market", conditions=[])}
    updated, _ = reduce_location_conditions(current, ctx)
    assert "guarded" in updated["market"]["conditions"]


def test_reduce_location_conditions_no_activity_deescalates():
    ctx = _make_seed_context(
        recent_consequences=[],
        encounter_aftermath={},
        faction_pressure_map={},
    )
    current = {"market": _make_location_condition("market", pressure="medium", conditions=[])}
    updated, _ = reduce_location_conditions(current, ctx)
    assert updated["market"]["pressure"] == "low"


def test_reduce_location_conditions_effects_have_correct_types():
    consequences = [{"id": "c1"}, {"id": "c2"}]
    ctx = _make_seed_context(recent_consequences=consequences)
    current = {"market": _make_location_condition("market")}
    _, effects = reduce_location_conditions(current, ctx)
    for eff in effects:
        assert eff["effect_type"] in SUPPORTED_WORLD_EFFECT_TYPES


def test_reduce_location_conditions_no_activity_adds_calm():
    ctx = _make_seed_context(
        recent_consequences=[],
        encounter_aftermath={},
        faction_pressure_map={},
    )
    current = {"market": _make_location_condition("market", conditions=[])}
    updated, _ = reduce_location_conditions(current, ctx)
    assert "calm" in updated["market"]["conditions"]


def test_reduce_location_conditions_high_faction_pressure_escalates():
    # Need some consequences to prevent the no-activity de-escalation branch
    ctx = _make_seed_context(
        faction_pressure_map={"guild_a": "high"},
        recent_consequences=[{"id": "c1"}],
    )
    current = {"market": _make_location_condition("market", pressure="low")}
    updated, _ = reduce_location_conditions(current, ctx)
    assert updated["market"]["pressure"] in ("medium", "high", "critical")


# ======================================================================
# Reducer tests — NPC activities
# ======================================================================


def test_reduce_npc_activities_deterministic():
    current = {"guard_a": _make_npc_activity("guard_a")}
    ctx = _make_seed_context(location_pressure={"market": "low"})
    r1 = reduce_npc_activities(dict(current), dict(ctx))
    r2 = reduce_npc_activities(dict(current), dict(ctx))
    assert r1[0] == r2[0]
    assert r1[1] == r2[1]


def test_reduce_npc_activities_pressure_maps_to_activity():
    ctx = _make_seed_context(location_pressure={"market": "critical"})
    current = {"guard_a": _make_npc_activity("guard_a", current_location="market")}
    updated, _ = reduce_npc_activities(current, ctx)
    assert updated["guard_a"]["activity"] == "patrolling"


def test_reduce_npc_activities_player_excluded():
    ctx = _make_seed_context(
        scene_entities=["player", "guard_a"],
        location_pressure={"market": "high"},
    )
    updated, _ = reduce_npc_activities({}, ctx)
    assert "player" not in updated
    assert "guard_a" in updated


def test_reduce_npc_activities_effects_on_activity_change():
    ctx = _make_seed_context(
        scene_entities=["guard_a"],
        location_pressure={"market": "high"},
    )
    current = {"guard_a": _make_npc_activity("guard_a", activity="idle",
                                              current_location="market")}
    _, effects = reduce_npc_activities(current, ctx)
    change_effects = [e for e in effects if e["effect_type"] == "npc_activity_changed"]
    assert len(change_effects) >= 1
    assert change_effects[0]["target_id"] == "guard_a"


def test_reduce_npc_activities_low_pressure_means_idle():
    ctx = _make_seed_context(
        scene_entities=["guard_a"],
        location_pressure={"market": "low"},
    )
    current = {"guard_a": _make_npc_activity("guard_a", current_location="market")}
    updated, _ = reduce_npc_activities(current, ctx)
    assert updated["guard_a"]["activity"] == "idle"


def test_reduce_npc_activities_medium_pressure_means_watchful():
    ctx = _make_seed_context(
        scene_entities=["guard_a"],
        location_pressure={"market": "medium"},
    )
    current = {"guard_a": _make_npc_activity("guard_a", activity="idle",
                                              current_location="market")}
    updated, _ = reduce_npc_activities(current, ctx)
    assert updated["guard_a"]["activity"] == "watchful"


# ======================================================================
# Reducer tests — world pressure
# ======================================================================


def test_reduce_world_pressure_deterministic():
    current = WorldPressureState()
    ctx = _make_seed_context()
    r1 = reduce_world_pressure(copy.deepcopy(current), dict(ctx))
    r2 = reduce_world_pressure(copy.deepcopy(current), dict(ctx))
    assert r1[0].to_dict() == r2[0].to_dict()
    assert r1[1] == r2[1]


def test_reduce_world_pressure_threads_escalate():
    current = WorldPressureState(pressure_by_thread={"t1": "low"})
    ctx = _make_seed_context(unresolved_threads=[{"thread_id": "t1"}])
    updated, _ = reduce_world_pressure(current, ctx)
    assert updated.pressure_by_thread["t1"] == "medium"


def test_reduce_world_pressure_encounter_aftermath_spikes_local():
    current = WorldPressureState()
    ctx = _make_seed_context(
        encounter_aftermath={"mode": "combat", "location": "market"},
        unresolved_threads=[],
    )
    updated, _ = reduce_world_pressure(current, ctx)
    assert updated.pressure_by_thread.get("market", "low") != "low"


def test_reduce_world_pressure_effects_on_change():
    current = WorldPressureState()
    ctx = _make_seed_context(
        unresolved_threads=[{"thread_id": "t1"}],
        faction_drift_current={"guild_a": {"pressure": "high"}},
        location_conditions_current={"market": {"pressure": "medium"}},
    )
    _, effects = reduce_world_pressure(current, ctx)
    assert len(effects) >= 1
    assert effects[0]["effect_type"] == "thread_pressure_changed"


# ======================================================================
# Reducer tests — trace builder
# ======================================================================


def test_build_world_sim_trace_returns_valid_dict():
    ctx = _make_seed_context()
    trace = build_world_sim_trace(
        ctx, [{"a": 1}], [{"b": 2}], [{"c": 3}], [], [], tick=1,
    )
    assert trace["tick"] == 1
    assert trace["total_effects"] == 3
    assert "seed_keys" in trace
    assert trace["faction_effect_count"] == 1
    assert trace["rumor_effect_count"] == 1
    assert trace["location_effect_count"] == 1


def test_build_world_sim_trace_empty_effects():
    ctx = _make_seed_context()
    trace = build_world_sim_trace(ctx, [], [], [], [], [], tick=None)
    assert trace["total_effects"] == 0
    assert trace["tick"] is None


# ======================================================================
# Controller tests
# ======================================================================


def test_controller_initializes_with_default_state():
    ctrl = WorldSimController()
    state = ctrl.get_state()
    assert isinstance(state, WorldSimState)
    assert state.sim_tick == 0
    assert state.status == "idle"


def test_controller_get_state_returns_world_sim_state():
    ctrl = WorldSimController()
    assert isinstance(ctrl.get_state(), WorldSimState)


def test_controller_advance_updates_only_world_sim_state():
    ctrl = WorldSimController()
    coherence = _MockCoherenceCore()
    social = _MockSocialStateCore()
    arc = _MockArcControlController()
    memory = CampaignMemoryCore()
    old_journal_len = len(memory.journal_entries)
    ctrl.advance(coherence, social, arc, memory, tick=1)
    # Memory journal should NOT be mutated by advance
    assert len(memory.journal_entries) == old_journal_len


def test_controller_advance_with_empty_inputs():
    ctrl = WorldSimController()
    result = ctrl.advance(None, None, None, None, tick=1)
    assert isinstance(result, WorldSimTickResult)
    assert result.advanced is True


def test_controller_advance_returns_tick_result():
    ctrl = WorldSimController()
    result = ctrl.advance(None, None, None, None, tick=1)
    assert result.advanced is True
    assert result.tick == 1


def test_controller_advance_increments_sim_tick():
    ctrl = WorldSimController()
    ctrl.advance(None, None, None, None, tick=5)
    assert ctrl.get_state().sim_tick == 5


def test_controller_advance_auto_increments_tick_when_none():
    ctrl = WorldSimController()
    ctrl.advance(None, None, None, None, tick=None)
    assert ctrl.get_state().sim_tick == 1
    ctrl.advance(None, None, None, None, tick=None)
    assert ctrl.get_state().sim_tick == 2


def test_controller_advance_trims_recent_effects():
    ctrl = WorldSimController()
    # Pre-fill with many effects
    ctrl.state.recent_effects = [{"i": i} for i in range(60)]
    ctrl.advance(None, None, None, None, tick=1)
    assert len(ctrl.get_state().recent_effects) <= 50


def test_controller_serialize_deserialize_roundtrip():
    ctrl = WorldSimController()
    ctrl.advance(None, None, None, None, tick=1)
    snapshot = ctrl.serialize_state()
    ctrl2 = WorldSimController()
    ctrl2.deserialize_state(snapshot)
    assert ctrl2.get_state().to_dict() == ctrl.get_state().to_dict()


def test_controller_to_dict_from_dict_roundtrip():
    ctrl = WorldSimController()
    ctrl.advance(None, None, None, None, tick=1)
    d = ctrl.to_dict()
    ctrl2 = WorldSimController.from_dict(d)
    assert ctrl2.get_state().to_dict() == ctrl.get_state().to_dict()


def test_controller_build_seed_context_none_inputs():
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(None, None, None, None)
    assert ctx["unresolved_threads"] == []
    assert ctx["recent_consequences"] == []
    assert ctx["known_factions"] == []
    assert ctx["recent_rumors"] == []
    assert ctx["arc_guidance"] == {}
    assert ctx["encounter_aftermath"] == {}
    assert ctx["known_locations"] == []


def test_controller_build_seed_context_extracts_locations():
    coherence = _MockCoherenceCore(locations=["market", "docks"])
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(coherence, None, None, None)
    assert "market" in ctx["known_locations"]
    assert "docks" in ctx["known_locations"]


def test_controller_build_seed_context_extracts_factions():
    social_state = _MockSocialState(
        alliances={"a1": _MockAlliance("guild_a", "guild_b")}
    )
    social = _MockSocialStateCore(state=social_state)
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(None, social, None, None)
    assert "guild_a" in ctx["known_factions"]
    assert "guild_b" in ctx["known_factions"]


def test_controller_build_seed_context_includes_arc_guidance():
    arc = _MockArcControlController(guidance={"pacing_pressure": "high"})
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(None, None, arc, None)
    assert ctx["arc_guidance"]["pacing_pressure"] == "high"


def test_controller_build_seed_context_includes_encounter_aftermath():
    enc_ctrl = EncounterController()
    enc_ctrl.start_encounter(
        mode="combat",
        scene_summary={"location": "market", "description": "A battle."},
        participants=[
            {"entity_id": "player", "role": "player"},
            {"entity_id": "goblin", "role": "enemy"},
        ],
        objectives=[{"objective_id": "o1", "kind": "defeat",
                      "progress": 0, "required": 1}],
        tick=1,
    )
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(None, None, None, None,
                                   encounter_controller=enc_ctrl)
    assert ctx["encounter_aftermath"].get("mode") == "combat"


def test_controller_advance_twice_deterministic():
    ctrl1 = WorldSimController()
    ctrl2 = WorldSimController()
    coherence = _MockCoherenceCore()
    social = _MockSocialStateCore()
    arc = _MockArcControlController()
    mem = CampaignMemoryCore()
    r1a = ctrl1.advance(coherence, social, arc, mem, tick=1)
    r1b = ctrl1.advance(coherence, social, arc, mem, tick=2)
    r2a = ctrl2.advance(coherence, social, arc, mem, tick=1)
    r2b = ctrl2.advance(coherence, social, arc, mem, tick=2)
    assert r1a.to_dict() == r2a.to_dict()
    assert r1b.to_dict() == r2b.to_dict()


def test_controller_recent_effects_bounded():
    ctrl = WorldSimController()
    for i in range(100):
        ctrl.advance(None, None, None, None, tick=i)
    assert len(ctrl.get_state().recent_effects) <= 50


def test_controller_advance_status_becomes_active():
    ctrl = WorldSimController()
    assert ctrl.get_state().status == "idle"
    ctrl.advance(None, None, None, None, tick=1)
    assert ctrl.get_state().status == "active"


def test_controller_advance_stores_last_result():
    ctrl = WorldSimController()
    result = ctrl.advance(None, None, None, None, tick=1)
    assert ctrl.get_state().last_result == result.to_dict()


# ======================================================================
# Presenter tests
# ======================================================================


def test_presenter_present_state_none_returns_defaults():
    presenter = WorldSimPresenter()
    out = presenter.present_state(None)
    assert out["sim_tick"] == 0
    assert out["status"] == "idle"
    assert out["notable_locations"] == []
    assert out["notable_factions"] == []
    assert out["rumor_heat"] == 0


def test_presenter_present_state_returns_compact_summary():
    state = WorldSimState(sim_tick=3, status="active")
    presenter = WorldSimPresenter()
    out = presenter.present_state(state)
    assert out["sim_tick"] == 3
    assert out["status"] == "active"
    assert "pressure_summary" in out


def test_presenter_present_state_includes_notable_locations():
    state = WorldSimState(
        location_conditions={
            "market": LocationConditionState(
                location_id="market", conditions=["tense"], pressure="high",
            )
        }
    )
    presenter = WorldSimPresenter()
    out = presenter.present_state(state)
    assert len(out["notable_locations"]) == 1
    assert out["notable_locations"][0]["location_id"] == "market"


def test_presenter_present_state_includes_notable_factions():
    state = WorldSimState(
        faction_drift={
            "guild_a": FactionDriftState(
                faction_id="guild_a", momentum="assertive", pressure="high",
            )
        }
    )
    presenter = WorldSimPresenter()
    out = presenter.present_state(state)
    assert len(out["notable_factions"]) == 1
    assert out["notable_factions"][0]["faction_id"] == "guild_a"


def test_presenter_present_state_includes_rumor_heat():
    state = WorldSimState(
        rumor_states={
            "r1": RumorPropagationState(rumor_id="r1", heat="warm"),
            "r2": RumorPropagationState(rumor_id="r2", heat="cold"),
            "r3": RumorPropagationState(rumor_id="r3", heat="hot"),
        }
    )
    presenter = WorldSimPresenter()
    out = presenter.present_state(state)
    assert out["rumor_heat"] == 2  # warm + hot


def test_presenter_present_recent_effects_none_returns_empty():
    presenter = WorldSimPresenter()
    out = presenter.present_recent_effects(None)
    assert out == []


def test_presenter_present_recent_effects_returns_summaries():
    state = WorldSimState(
        recent_effects=[
            {"effect_type": "faction_shift", "scope": "faction",
             "target_id": "guild_a",
             "payload": {"new_momentum": "assertive", "new_pressure": "high"}},
        ]
    )
    presenter = WorldSimPresenter()
    out = presenter.present_recent_effects(state)
    assert len(out) == 1
    assert "summary" in out[0]
    assert "guild_a" in out[0]["summary"]


def test_presenter_present_tick_result_none_returns_defaults():
    presenter = WorldSimPresenter()
    out = presenter.present_tick_result(None)
    assert out["tick"] is None
    assert out["advanced"] is False
    assert out["effect_count"] == 0
    assert out["summary_count"] == 0
    assert out["journal_count"] == 0


def test_presenter_present_tick_result_includes_counts():
    result = WorldSimTickResult(
        tick=5, advanced=True,
        generated_effects=[{"e": 1}, {"e": 2}],
        generated_summaries=[{"s": 1}],
        journal_payloads=[{"j": 1}],
    )
    presenter = WorldSimPresenter()
    out = presenter.present_tick_result(result)
    assert out["tick"] == 5
    assert out["effect_count"] == 2
    assert out["summary_count"] == 1
    assert out["journal_count"] == 1


def test_presenter_present_journal_payloads_none_returns_empty():
    presenter = WorldSimPresenter()
    out = presenter.present_journal_payloads(None)
    assert out == []


def test_presenter_present_journal_payloads_returns_journalable():
    result = WorldSimTickResult(
        journal_payloads=[
            {"effect_type": "faction_shift", "journalable": True},
            {"effect_type": "rumor_spread", "journalable": True},
        ],
    )
    presenter = WorldSimPresenter()
    out = presenter.present_journal_payloads(result)
    assert len(out) == 2


# ======================================================================
# Journal builder tests
# ======================================================================


def test_journal_builder_non_journalable_returns_none():
    builder = JournalBuilder()
    entry = builder.build_world_sim_log_entry(
        {"effect_type": "npc_activity_changed"}, tick=1,
    )
    assert entry is None


def test_journal_builder_faction_shift_returns_entry():
    builder = JournalBuilder()
    entry = builder.build_world_sim_log_entry(
        {
            "effect_type": "faction_shift",
            "effect_id": "fs:guild_a:1",
            "target_id": "guild_a",
            "scope": "faction",
            "payload": {"new_momentum": "assertive", "new_pressure": "high"},
        },
        tick=1,
    )
    assert entry is not None
    assert entry.entry_type == "world_sim"
    assert "guild_a" in entry.summary


def test_journal_builder_rumor_spread_returns_entry():
    builder = JournalBuilder()
    entry = builder.build_world_sim_log_entry(
        {
            "effect_type": "rumor_spread",
            "effect_id": "rs:r1:1",
            "target_id": "rumor_1",
            "scope": "rumor",
            "payload": {"spread_to": "market"},
        },
        tick=1,
    )
    assert entry is not None
    assert entry.entry_type == "world_sim"
    assert "rumor_1" in entry.summary


def test_journal_builder_location_condition_changed_returns_entry():
    builder = JournalBuilder()
    entry = builder.build_world_sim_log_entry(
        {
            "effect_type": "location_condition_changed",
            "effect_id": "lcc:market:1",
            "target_id": "market",
            "scope": "location",
            "payload": {"new_conditions": ["tense"]},
        },
        tick=1,
    )
    assert entry is not None
    assert "market" in entry.summary


def test_journal_builder_thread_pressure_returns_entry():
    builder = JournalBuilder()
    entry = builder.build_world_sim_log_entry(
        {
            "effect_type": "thread_pressure_changed",
            "effect_id": "tpc:1",
            "target_id": None,
            "scope": "world",
            "payload": {"thread_count": 3},
        },
        tick=1,
    )
    assert entry is not None
    assert "3" in entry.summary


def test_journal_builder_entry_type_is_world_sim():
    builder = JournalBuilder()
    for etype in ("faction_shift", "rumor_spread", "location_condition_changed",
                  "thread_pressure_changed"):
        entry = builder.build_world_sim_log_entry(
            {"effect_type": etype, "effect_id": f"e:{etype}",
             "target_id": "t", "scope": "s", "payload": {}},
            tick=1,
        )
        assert entry is not None
        assert entry.entry_type == "world_sim"


def test_journal_builder_entry_id_is_deterministic():
    builder = JournalBuilder()
    e1 = builder.build_world_sim_log_entry(
        {"effect_type": "faction_shift", "effect_id": "fs:g:1",
         "target_id": "g", "scope": "faction", "payload": {}},
        tick=1,
    )
    e2 = builder.build_world_sim_log_entry(
        {"effect_type": "faction_shift", "effect_id": "fs:g:1",
         "target_id": "g", "scope": "faction", "payload": {}},
        tick=1,
    )
    assert e1.entry_id == e2.entry_id


# ======================================================================
# Memory core tests
# ======================================================================


def test_memory_core_records_meaningful_entry():
    core = CampaignMemoryCore()
    core.record_world_sim_log_entry(
        {"effect_type": "faction_shift", "effect_id": "fs:g:1",
         "target_id": "guild_a", "scope": "faction",
         "payload": {"new_momentum": "assertive", "new_pressure": "high"}},
        tick=1,
    )
    assert len(core.journal_entries) == 1
    assert core.journal_entries[0].entry_type == "world_sim"


def test_memory_core_skips_non_journalable():
    core = CampaignMemoryCore()
    core.record_world_sim_log_entry(
        {"effect_type": "npc_activity_changed", "effect_id": "npc:1",
         "target_id": "guard_a", "scope": "npc", "payload": {}},
        tick=1,
    )
    assert len(core.journal_entries) == 0


def test_memory_core_trims_journal():
    core = CampaignMemoryCore()
    core._max_entries = 5
    for i in range(10):
        core.record_world_sim_log_entry(
            {"effect_type": "faction_shift", "effect_id": f"fs:{i}",
             "target_id": "g", "scope": "faction", "payload": {}},
            tick=i,
        )
    assert len(core.journal_entries) <= 5


# ======================================================================
# Coherence query helper tests
# ======================================================================


def test_coherence_get_known_locations():
    coherence = _MockCoherenceCore(locations=["docks", "market", "tavern"])
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(coherence, None, None, None)
    assert sorted(ctx["known_locations"]) == ["docks", "market", "tavern"]


def test_coherence_get_active_scene_location():
    coherence = _MockCoherenceCore(scene_location="docks")
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(coherence, None, None, None)
    assert ctx["active_scene_location"] == "docks"


def test_coherence_get_active_threads():
    threads = [{"thread_id": "t1", "title": "Thread One"}]
    coherence = _MockCoherenceCore(threads=threads)
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(coherence, None, None, None)
    assert len(ctx["unresolved_threads"]) == 1
    assert ctx["unresolved_threads"][0]["thread_id"] == "t1"


def test_coherence_get_scene_entities():
    coherence = _MockCoherenceCore(entities=["player", "npc_a", "npc_b"])
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(coherence, None, None, None)
    assert "player" in ctx["scene_entities"]
    assert "npc_a" in ctx["scene_entities"]


# ======================================================================
# Social state query helper tests
# ======================================================================


def test_social_get_known_factions():
    state = _MockSocialState(
        alliances={"a1": _MockAlliance("guild_a", "guild_b")}
    )
    social = _MockSocialStateCore(state=state)
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(None, social, None, None)
    assert "guild_a" in ctx["known_factions"]
    assert "guild_b" in ctx["known_factions"]


def test_social_get_recent_rumors():
    state = _MockSocialState(
        rumors={"r1": _MockRumor("r1", active=True)}
    )
    social = _MockSocialStateCore(state=state)
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(None, social, None, None)
    assert len(ctx["recent_rumors"]) == 1


def test_social_get_faction_pressure_map():
    state = _MockSocialState(
        relationships={
            "rel_1": _MockRelationship("guild_a", "guild_b", "hostile")
        }
    )
    social = _MockSocialStateCore(state=state)
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(None, social, None, None)
    assert ctx["faction_pressure_map"].get("guild_a") == "high"


def test_social_get_relationship_hotspots_via_pressure_map():
    state = _MockSocialState(
        relationships={
            "rel_1": _MockRelationship("guild_a", "guild_b", "enemy"),
        }
    )
    social = _MockSocialStateCore(state=state)
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(None, social, None, None)
    assert "guild_a" in ctx["faction_pressure_map"]


# ======================================================================
# Arc control guidance tests
# ======================================================================


def test_arc_guidance_returns_guidance_dict():
    arc = _MockArcControlController()
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(None, None, arc, None)
    assert isinstance(ctx["arc_guidance"], dict)


def test_arc_guidance_includes_pacing_pressure():
    arc = _MockArcControlController(guidance={
        "pacing_pressure": "high",
        "reveal_pressure": "normal",
    })
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(None, None, arc, None)
    assert ctx["arc_guidance"]["pacing_pressure"] == "high"


def test_arc_guidance_includes_reveal_pressure():
    arc = _MockArcControlController(guidance={
        "pacing_pressure": "normal",
        "reveal_pressure": "high",
    })
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(None, None, arc, None)
    assert ctx["arc_guidance"]["reveal_pressure"] == "high"


def test_arc_guidance_none_controller():
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(None, None, None, None)
    assert ctx["arc_guidance"] == {}


# ======================================================================
# Encounter controller tests
# ======================================================================


def test_encounter_build_world_sim_seed_no_active():
    enc_ctrl = EncounterController()
    seed = enc_ctrl.build_world_sim_seed()
    assert seed == {}


def test_encounter_build_world_sim_seed_active():
    enc_ctrl = EncounterController()
    enc_ctrl.start_encounter(
        mode="combat",
        scene_summary={"location": "market", "description": "Battle."},
        participants=[
            {"entity_id": "player", "role": "player"},
            {"entity_id": "goblin", "role": "enemy"},
        ],
        objectives=[{"objective_id": "o1", "kind": "defeat",
                      "progress": 0, "required": 1}],
        tick=1,
    )
    seed = enc_ctrl.build_world_sim_seed()
    assert seed["mode"] == "combat"
    assert "status" in seed
    assert "pressure" in seed


# ======================================================================
# UX model tests
# ======================================================================


def test_scene_ux_payload_has_world_field():
    payload = SceneUXPayload(
        payload_id="p1",
        scene={"location": "market"},
        world={"sim_tick": 1},
    )
    assert payload.world == {"sim_tick": 1}


def test_scene_ux_payload_to_dict_includes_world():
    payload = SceneUXPayload(
        payload_id="p1",
        scene={"location": "market"},
        world={"sim_tick": 1},
    )
    d = payload.to_dict()
    assert "world" in d
    assert d["world"]["sim_tick"] == 1


def test_scene_ux_payload_from_dict_restores_world():
    d = {
        "payload_id": "p1",
        "scene": {"location": "market"},
        "world": {"sim_tick": 1, "status": "active"},
    }
    payload = SceneUXPayload.from_dict(d)
    assert payload.world["sim_tick"] == 1
    assert payload.world["status"] == "active"


def test_action_result_payload_has_world_field():
    payload = ActionResultPayload(
        result_id="r1",
        action_result={"outcome": "success"},
        world={"sim_tick": 2},
    )
    assert payload.world == {"sim_tick": 2}


def test_action_result_payload_to_dict_includes_world():
    payload = ActionResultPayload(
        result_id="r1",
        action_result={"outcome": "success"},
        world={"sim_tick": 2},
    )
    d = payload.to_dict()
    assert "world" in d
    assert d["world"]["sim_tick"] == 2


def test_action_result_payload_from_dict_restores_world():
    d = {
        "result_id": "r1",
        "action_result": {"outcome": "success"},
        "world": {"sim_tick": 2, "status": "active"},
    }
    payload = ActionResultPayload.from_dict(d)
    assert payload.world["sim_tick"] == 2
    assert payload.world["status"] == "active"


# ======================================================================
# Additional edge-case tests
# ======================================================================


def test_world_effect_to_dict_payload_is_copy():
    obj = WorldEffect(effect_id="e1", effect_type="t", scope="s",
                       payload={"key": "value"})
    d = obj.to_dict()
    d["payload"]["key"] = "modified"
    # to_dict does a shallow dict copy, so top-level keys are independent
    assert obj.payload["key"] == "value"


def test_faction_drift_recent_changes_trimmed_by_reducer():
    changes = [{"i": i} for i in range(15)]
    current = {"guild_a": _make_faction_drift(
        "guild_a", recent_changes=changes,
    )}
    ctx = _make_seed_context()
    updated, _ = reduce_faction_drift(current, ctx)
    assert len(updated["guild_a"]["recent_changes"]) <= 10


def test_rumor_propagation_hot_to_warm_on_full_spread():
    current = {"r1": _make_rumor_state(
        "r1", heat="hot", status="active",
        current_locations=["a", "b", "c", "d", "e"], reach=5,
    )}
    ctx = _make_seed_context(known_locations=["a", "b", "c", "d", "e"])
    updated, _ = reduce_rumor_propagation(current, ctx)
    assert updated["r1"]["heat"] == "warm"


def test_location_conditions_bounded_to_five():
    current = {"market": _make_location_condition(
        "market", conditions=["a", "b", "c", "d", "e"],
    )}
    ctx = _make_seed_context(recent_consequences=[{"id": "c1"}, {"id": "c2"}])
    updated, _ = reduce_location_conditions(current, ctx)
    assert len(updated["market"]["conditions"]) <= 5


def test_npc_activity_last_update_tick_set():
    ctx = _make_seed_context(
        scene_entities=["guard_a"],
        location_pressure={"market": "low"},
        tick=42,
    )
    updated, _ = reduce_npc_activities({}, ctx)
    assert updated["guard_a"]["last_update_tick"] == 42


def test_controller_build_seed_context_tick_passed():
    ctrl = WorldSimController()
    ctx = ctrl.build_seed_context(None, None, None, None, tick=99)
    assert ctx["tick"] == 99


def test_presenter_present_state_no_notable_factions_when_steady_low():
    state = WorldSimState(
        faction_drift={
            "guild_a": FactionDriftState(
                faction_id="guild_a", momentum="steady", pressure="low",
            )
        }
    )
    presenter = WorldSimPresenter()
    out = presenter.present_state(state)
    assert len(out["notable_factions"]) == 0


def test_presenter_present_state_no_notable_locations_when_empty_conditions():
    state = WorldSimState(
        location_conditions={
            "market": LocationConditionState(
                location_id="market", conditions=[],
            )
        }
    )
    presenter = WorldSimPresenter()
    out = presenter.present_state(state)
    assert len(out["notable_locations"]) == 0


def test_controller_advance_generates_summaries_when_effects_exist():
    ctrl = WorldSimController()
    coherence = _MockCoherenceCore(
        locations=["market"],
        scene_location="market",
        consequences=[{"id": "c1"}, {"id": "c2"}],
    )
    result = ctrl.advance(coherence, None, None, None, tick=1)
    if result.generated_effects:
        assert len(result.generated_summaries) >= 1
        assert result.generated_summaries[0]["summary_type"] == "world_sim_tick"


def test_controller_advance_journal_payloads_are_journalable():
    ctrl = WorldSimController()
    coherence = _MockCoherenceCore(
        locations=["market"],
        scene_location="market",
        consequences=[{"id": "c1"}, {"id": "c2"}],
    )
    result = ctrl.advance(coherence, None, None, None, tick=1)
    for jp in result.journal_payloads:
        assert jp.get("journalable", False) is True


def test_world_sim_state_from_dict_nested_objects():
    d = {
        "sim_tick": 5,
        "status": "active",
        "faction_drift": {
            "guild_a": {
                "faction_id": "guild_a",
                "momentum": "assertive",
                "pressure": "high",
            }
        },
        "rumor_states": {
            "r1": {
                "rumor_id": "r1",
                "heat": "warm",
                "status": "active",
            }
        },
        "location_conditions": {
            "market": {
                "location_id": "market",
                "conditions": ["tense"],
            }
        },
        "npc_activities": {
            "guard_a": {
                "entity_id": "guard_a",
                "activity": "patrolling",
            }
        },
        "world_pressure": {
            "active_threads": ["t1"],
            "pressure_by_thread": {"t1": "medium"},
        },
    }
    state = WorldSimState.from_dict(d)
    assert state.sim_tick == 5
    assert state.faction_drift["guild_a"].momentum == "assertive"
    assert state.rumor_states["r1"].heat == "warm"
    assert state.location_conditions["market"].conditions == ["tense"]
    assert state.npc_activities["guard_a"].activity == "patrolling"
    assert state.world_pressure.active_threads == ["t1"]


def test_world_pressure_state_preserves_metadata():
    obj = WorldPressureState(metadata={"key": "val"})
    d = obj.to_dict()
    restored = WorldPressureState.from_dict(d)
    assert restored.metadata == {"key": "val"}


def test_reduce_faction_drift_multiple_factions():
    ctx = _make_seed_context(known_factions=["guild_a", "guild_b", "guild_c"])
    current = {
        "guild_a": _make_faction_drift("guild_a"),
        "guild_b": _make_faction_drift("guild_b"),
    }
    updated, _ = reduce_faction_drift(current, ctx)
    assert "guild_a" in updated
    assert "guild_b" in updated
    assert "guild_c" in updated


def test_reduce_npc_activities_high_pressure_searching():
    ctx = _make_seed_context(
        scene_entities=["guard_a"],
        location_pressure={"market": "high"},
    )
    current = {"guard_a": _make_npc_activity("guard_a", current_location="market")}
    updated, _ = reduce_npc_activities(current, ctx)
    assert updated["guard_a"]["activity"] == "searching"


def test_reduce_world_pressure_faction_pressure_from_drift():
    current = WorldPressureState()
    ctx = _make_seed_context(
        unresolved_threads=[],
        faction_drift_current={"guild_a": {"pressure": "high"}},
        location_conditions_current={},
    )
    updated, _ = reduce_world_pressure(current, ctx)
    assert updated.pressure_by_faction.get("guild_a") == "high"


def test_reduce_world_pressure_location_pressure_from_conditions():
    current = WorldPressureState()
    ctx = _make_seed_context(
        unresolved_threads=[],
        faction_drift_current={},
        location_conditions_current={"market": {"pressure": "medium"}},
    )
    updated, _ = reduce_world_pressure(current, ctx)
    assert updated.pressure_by_location.get("market") == "medium"


def test_presenter_effect_summary_npc_activity():
    presenter = WorldSimPresenter()
    state = WorldSimState(
        recent_effects=[
            {"effect_type": "npc_activity_changed", "scope": "npc",
             "target_id": "guard_a",
             "payload": {"new_activity": "patrolling"}},
        ]
    )
    out = presenter.present_recent_effects(state)
    assert "patrolling" in out[0]["summary"]


def test_presenter_effect_summary_rumor_cools():
    presenter = WorldSimPresenter()
    state = WorldSimState(
        recent_effects=[
            {"effect_type": "rumor_cools", "scope": "rumor",
             "target_id": "r1", "payload": {}},
        ]
    )
    out = presenter.present_recent_effects(state)
    assert "cooled" in out[0]["summary"]


def test_presenter_effect_summary_thread_pressure():
    presenter = WorldSimPresenter()
    state = WorldSimState(
        recent_effects=[
            {"effect_type": "thread_pressure_changed", "scope": "world",
             "target_id": None,
             "payload": {"thread_count": 2}},
        ]
    )
    out = presenter.present_recent_effects(state)
    assert "2" in out[0]["summary"]


def test_presenter_present_state_pressure_summary_keys():
    state = WorldSimState(
        world_pressure=WorldPressureState(
            active_threads=["t1"],
            pressure_by_thread={"t1": "medium"},
            pressure_by_location={"market": "low"},
            pressure_by_faction={"guild_a": "high"},
        )
    )
    presenter = WorldSimPresenter()
    out = presenter.present_state(state)
    ps = out["pressure_summary"]
    assert ps["active_threads"] == 1
    assert ps["thread_pressure_count"] == 1
    assert ps["location_pressure_count"] == 1
    assert ps["faction_pressure_count"] == 1


def test_memory_core_multiple_entries_accumulate():
    core = CampaignMemoryCore()
    for i in range(3):
        core.record_world_sim_log_entry(
            {"effect_type": "faction_shift", "effect_id": f"fs:{i}",
             "target_id": "g", "scope": "faction", "payload": {}},
            tick=i,
        )
    assert len(core.journal_entries) == 3


def test_scene_ux_payload_default_world_is_empty():
    payload = SceneUXPayload(payload_id="p1", scene={})
    assert payload.world == {}


def test_action_result_payload_default_world_is_empty():
    payload = ActionResultPayload(result_id="r1", action_result={})
    assert payload.world == {}


def test_reduce_rumor_propagation_warm_no_spread_target_cools():
    current = {"r1": _make_rumor_state(
        "r1", heat="warm", status="active",
        current_locations=["market"], reach=1,
    )}
    ctx = _make_seed_context(known_locations=["market"])
    updated, _ = reduce_rumor_propagation(current, ctx)
    assert updated["r1"]["heat"] == "cold"
    assert updated["r1"]["status"] == "dormant"


def test_controller_advance_with_coherence_and_social():
    ctrl = WorldSimController()
    coherence = _MockCoherenceCore(
        locations=["market", "docks"],
        entities=["player", "guard_a"],
    )
    state = _MockSocialState(
        alliances={"a1": _MockAlliance("guild_a", "guild_b")}
    )
    social = _MockSocialStateCore(state=state)
    arc = _MockArcControlController()
    result = ctrl.advance(coherence, social, arc, None, tick=1)
    assert result.advanced is True
    s = ctrl.get_state()
    assert s.sim_tick == 1
    assert s.status == "active"
