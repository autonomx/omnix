"""Phase 8.3 — World Simulation Regression Tests.

Protect architectural boundaries: no direct truth mutation of outside
systems (coherence, social, memory, arc, encounter), deterministic
outputs for identical inputs, snapshot-safe roundtrips, supported
effect-type guardrails, and bounded state growth.

Run with:
    cd src && PYTHONPATH="." python3 -m pytest \
        tests/regression/test_phase83_world_sim_regression.py -v --noconftest
"""

from __future__ import annotations

import copy
import sys
import os
from typing import Any
from unittest.mock import MagicMock

# Ensure the src directory is on sys.path for import resolution.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.rpg.world_sim.controller import WorldSimController, _MAX_RECENT_EFFECTS
from app.rpg.world_sim.models import (
    SUPPORTED_WORLD_EFFECT_TYPES,
    WorldSimState,
    WorldSimTickResult,
)
from app.rpg.world_sim.presenter import WorldSimPresenter
from app.rpg.world_sim.reducers import (
    reduce_faction_drift,
    reduce_location_conditions,
    reduce_npc_activities,
    reduce_rumor_propagation,
)


# ------------------------------------------------------------------
# Mock helpers
# ------------------------------------------------------------------


class _MockCoherenceQuery:
    """Minimal coherence query interface consumed by build_seed_context."""

    def __init__(
        self,
        locations: list[str] | None = None,
        scene_location: str | None = None,
        threads: list[dict] | None = None,
        consequences: list[dict] | None = None,
        entities: list[str] | None = None,
    ) -> None:
        self._locations = locations or ["market", "docks"]
        self._scene_location = scene_location or "market"
        self._threads = threads or []
        self._consequences = consequences or []
        self._entities = entities or ["player", "guard_a"]

    def get_known_locations(self) -> list[str]:
        return list(self._locations)

    def get_scene_summary(self) -> dict:
        return {"location": self._scene_location, "summary": "A scene."}

    def get_unresolved_threads(self) -> list[dict]:
        return list(self._threads)

    def get_recent_consequences(self, limit: int = 5) -> list[dict]:
        return list(self._consequences[:limit])

    def get_scene_entities(self) -> list[str]:
        return list(self._entities)


class _MockCoherenceCore:
    """Mimics the coherence core the controller reads via .query."""

    def __init__(self, **kw: Any) -> None:
        self.query = _MockCoherenceQuery(**kw)


class _MockAlliance:
    def __init__(self, entity_a: str, entity_b: str) -> None:
        self.entity_a = entity_a
        self.entity_b = entity_b


class _MockRumor:
    def __init__(self, rumor_id: str, active: bool = True, **kw: Any) -> None:
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
    def __init__(self, source_id: str, target_id: str, status: str = "neutral") -> None:
        self.source_id = source_id
        self.target_id = target_id
        self.status = status


class _MockSocialState:
    def __init__(
        self,
        alliances: dict | None = None,
        rumors: dict | None = None,
        relationships: dict | None = None,
    ) -> None:
        self.alliances = alliances or {}
        self.rumors = rumors or {}
        self.relationships = relationships or {}


class _MockSocialStateCore:
    """Mimics social state core consumed by build_seed_context."""

    def __init__(self, state: _MockSocialState | None = None) -> None:
        self._state = state or _MockSocialState()

    def get_state(self) -> _MockSocialState:
        return self._state

    def get_query(self) -> _MockSocialStateCore:
        return self


class _MockArcControlController:
    def __init__(self, guidance: dict | None = None) -> None:
        self._guidance = guidance or {
            "top_active_arcs": [],
            "reveal_pressure": "normal",
            "pacing_pressure": "normal",
            "escalation_bias": "neutral",
            "preferred_thread_pressure_targets": [],
        }

    def build_world_sim_guidance(self) -> dict:
        return dict(self._guidance)


class _MockEncounterController:
    def __init__(self, seed: dict | None = None) -> None:
        self._seed = seed or {}

    def build_world_sim_seed(self) -> dict:
        return dict(self._seed)


class _MockCampaignMemoryCore:
    """Campaign memory core — world sim should never mutate it."""
    pass


def _make_seed_context(**overrides: Any) -> dict:
    """Build a minimal seed context dict with sane defaults."""
    ctx: dict[str, Any] = {
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


def _make_default_mocks() -> dict[str, Any]:
    """Return a dict of keyword args for WorldSimController.advance()."""
    return {
        "coherence_core": _MockCoherenceCore(),
        "social_state_core": _MockSocialStateCore(),
        "arc_control_controller": _MockArcControlController(),
        "campaign_memory_core": _MockCampaignMemoryCore(),
        "encounter_controller": _MockEncounterController(),
        "tick": 1,
    }


# ==================================================================
# 1. No direct mutation of outside truth owners
# ==================================================================


def test_advance_does_not_mutate_coherence_core() -> None:
    """advance() must never mutate the coherence core it reads."""
    coherence = _MockCoherenceCore(
        threads=[{"thread_id": "t1", "status": "active"}],
        consequences=[{"consequence_id": "c1"}],
    )
    state_before = copy.deepcopy(coherence.__dict__)

    ctrl = WorldSimController()
    ctrl.advance(
        coherence_core=coherence,
        social_state_core=_MockSocialStateCore(),
        arc_control_controller=_MockArcControlController(),
        campaign_memory_core=_MockCampaignMemoryCore(),
        encounter_controller=_MockEncounterController(),
        tick=1,
    )

    state_after = copy.deepcopy(coherence.__dict__)
    # Compare the query sub-object attributes
    assert coherence.query._threads == [{"thread_id": "t1", "status": "active"}]
    assert coherence.query._consequences == [{"consequence_id": "c1"}]


def test_advance_does_not_mutate_social_state_core() -> None:
    """advance() must never mutate the social state core it reads."""
    social_state = _MockSocialState(
        alliances={"a1": _MockAlliance("faction_x", "faction_y")},
        rumors={"r1": _MockRumor("r1", active=True)},
        relationships={"rel1": _MockRelationship("faction_x", "faction_y", "hostile")},
    )
    social = _MockSocialStateCore(state=social_state)
    alliances_before = list(social_state.alliances.keys())
    rumors_before = list(social_state.rumors.keys())
    relationships_before = list(social_state.relationships.keys())

    ctrl = WorldSimController()
    ctrl.advance(
        coherence_core=_MockCoherenceCore(),
        social_state_core=social,
        arc_control_controller=_MockArcControlController(),
        campaign_memory_core=_MockCampaignMemoryCore(),
        encounter_controller=_MockEncounterController(),
        tick=1,
    )

    assert list(social_state.alliances.keys()) == alliances_before
    assert list(social_state.rumors.keys()) == rumors_before
    assert list(social_state.relationships.keys()) == relationships_before


def test_advance_does_not_mutate_arc_controller() -> None:
    """advance() must never mutate the arc control controller."""
    arc = _MockArcControlController(guidance={"escalation_bias": "hawkish"})
    guidance_before = copy.deepcopy(arc._guidance)

    ctrl = WorldSimController()
    ctrl.advance(**{**_make_default_mocks(), "arc_control_controller": arc})

    assert arc._guidance == guidance_before


def test_advance_does_not_mutate_memory_core() -> None:
    """advance() must never mutate the campaign memory core."""
    memory = MagicMock(name="campaign_memory_core")

    ctrl = WorldSimController()
    ctrl.advance(**{**_make_default_mocks(), "campaign_memory_core": memory})

    memory.assert_not_called()
    assert memory.method_calls == []


def test_advance_does_not_mutate_encounter_controller() -> None:
    """advance() must never mutate the encounter controller."""
    encounter = _MockEncounterController(seed={"mode": "combat", "location": "arena"})
    seed_before = copy.deepcopy(encounter._seed)

    ctrl = WorldSimController()
    ctrl.advance(**{**_make_default_mocks(), "encounter_controller": encounter})

    assert encounter._seed == seed_before


# ==================================================================
# 2. Same state => same world sim result (determinism)
# ==================================================================


def test_reduce_faction_drift_determinism() -> None:
    """Identical inputs to reduce_faction_drift produce identical outputs."""
    ctx = _make_seed_context(
        unresolved_threads=[
            {"thread_id": "guild_a_debt", "status": "active"},
            {"thread_id": "guild_a_rivalry", "status": "active"},
        ],
        faction_pressure_map={"guild_b": "high"},
    )
    current: dict[str, dict] = {}

    result_a = reduce_faction_drift(copy.deepcopy(current), copy.deepcopy(ctx))
    result_b = reduce_faction_drift(copy.deepcopy(current), copy.deepcopy(ctx))

    assert result_a == result_b


def test_reduce_rumor_propagation_determinism() -> None:
    """Identical inputs to reduce_rumor_propagation produce identical outputs."""
    ctx = _make_seed_context(
        recent_rumors=[{
            "rumor_id": "r1",
            "source_npc_id": "npc_a",
            "subject_id": "target_b",
            "summary": "Heard something.",
            "location": "tavern",
        }],
    )
    current: dict[str, dict] = {}

    result_a = reduce_rumor_propagation(copy.deepcopy(current), copy.deepcopy(ctx))
    result_b = reduce_rumor_propagation(copy.deepcopy(current), copy.deepcopy(ctx))

    assert result_a == result_b


def test_reduce_location_conditions_determinism() -> None:
    """Identical inputs to reduce_location_conditions produce identical outputs."""
    ctx = _make_seed_context(
        recent_consequences=[{"id": "c1"}, {"id": "c2"}],
        encounter_aftermath={"mode": "combat", "location": "market"},
    )
    current: dict[str, dict] = {}

    result_a = reduce_location_conditions(copy.deepcopy(current), copy.deepcopy(ctx))
    result_b = reduce_location_conditions(copy.deepcopy(current), copy.deepcopy(ctx))

    assert result_a == result_b


def test_reduce_npc_activities_determinism() -> None:
    """Identical inputs to reduce_npc_activities produce identical outputs."""
    ctx = _make_seed_context(
        location_pressure={"market": "high", "docks": "low"},
    )
    current: dict[str, dict] = {}

    result_a = reduce_npc_activities(copy.deepcopy(current), copy.deepcopy(ctx))
    result_b = reduce_npc_activities(copy.deepcopy(current), copy.deepcopy(ctx))

    assert result_a == result_b


def test_full_advance_determinism() -> None:
    """Two identical controllers with identical inputs produce identical results."""
    mocks = _make_default_mocks()

    ctrl_a = WorldSimController()
    ctrl_b = WorldSimController()

    result_a = ctrl_a.advance(**copy.deepcopy(mocks))
    result_b = ctrl_b.advance(**copy.deepcopy(mocks))

    assert result_a.to_dict() == result_b.to_dict()


def test_full_advance_determinism_with_rich_context() -> None:
    """Determinism holds with non-trivial coherence/social inputs."""
    coherence_kw = {
        "threads": [
            {"thread_id": "guild_a_tension", "status": "active"},
            {"thread_id": "guild_a_threat", "status": "active"},
        ],
        "consequences": [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}],
        "entities": ["player", "guard_a", "merchant_b"],
        "locations": ["market", "docks", "tavern"],
        "scene_location": "market",
    }
    social_state = _MockSocialState(
        alliances={"a1": _MockAlliance("guild_a", "guild_b")},
        rumors={"r1": _MockRumor("r1", active=True)},
        relationships={"rel1": _MockRelationship("guild_a", "guild_b", "hostile")},
    )

    def _build_mocks() -> dict:
        return {
            "coherence_core": _MockCoherenceCore(**coherence_kw),
            "social_state_core": _MockSocialStateCore(
                state=_MockSocialState(
                    alliances={"a1": _MockAlliance("guild_a", "guild_b")},
                    rumors={"r1": _MockRumor("r1", active=True)},
                    relationships={
                        "rel1": _MockRelationship("guild_a", "guild_b", "hostile"),
                    },
                )
            ),
            "arc_control_controller": _MockArcControlController(),
            "campaign_memory_core": _MockCampaignMemoryCore(),
            "encounter_controller": _MockEncounterController(
                seed={"mode": "combat", "location": "market"},
            ),
            "tick": 5,
        }

    ctrl_a = WorldSimController()
    ctrl_b = WorldSimController()

    result_a = ctrl_a.advance(**_build_mocks())
    result_b = ctrl_b.advance(**_build_mocks())

    assert result_a.to_dict() == result_b.to_dict()
    assert ctrl_a.serialize_state() == ctrl_b.serialize_state()


# ==================================================================
# 3. Snapshot roundtrip
# ==================================================================


def test_snapshot_roundtrip_fresh_controller() -> None:
    """A freshly-created controller survives serialize/deserialize."""
    ctrl = WorldSimController()
    data = ctrl.serialize_state()
    restored = WorldSimController()
    restored.deserialize_state(data)

    assert ctrl.serialize_state() == restored.serialize_state()


def test_snapshot_roundtrip_after_advance() -> None:
    """Controller state survives roundtrip after advance populates it."""
    ctrl = WorldSimController()
    ctrl.advance(**_make_default_mocks())

    data = ctrl.serialize_state()
    restored = WorldSimController()
    restored.deserialize_state(data)

    assert ctrl.serialize_state() == restored.serialize_state()


def test_snapshot_roundtrip_presenter_payloads_match() -> None:
    """Presenter output is identical for original and restored state."""
    ctrl = WorldSimController()
    ctrl.advance(**_make_default_mocks())

    data = ctrl.serialize_state()
    restored = WorldSimController()
    restored.deserialize_state(data)

    presenter = WorldSimPresenter()
    payload_orig = presenter.present_state(ctrl.get_state())
    payload_rest = presenter.present_state(restored.get_state())

    assert payload_orig == payload_rest


# ==================================================================
# 4. Only supported effect types emitted
# ==================================================================


def test_all_reducer_effects_have_supported_types() -> None:
    """Every effect_type emitted by reducers is in SUPPORTED_WORLD_EFFECT_TYPES."""
    ctx = _make_seed_context(
        unresolved_threads=[
            {"thread_id": "guild_a_plot", "status": "active"},
            {"thread_id": "guild_a_scheme", "status": "active"},
        ],
        recent_consequences=[{"id": "c1"}, {"id": "c2"}, {"id": "c3"}],
        recent_rumors=[{
            "rumor_id": "r1",
            "source_npc_id": "npc_a",
            "subject_id": "sub_b",
            "summary": "Whisper.",
            "location": "tavern",
        }],
        encounter_aftermath={"mode": "combat", "location": "market"},
        faction_pressure_map={"guild_a": "high"},
        location_pressure={"market": "high", "docks": "low", "tavern": "medium"},
    )

    _, faction_effects = reduce_faction_drift({}, copy.deepcopy(ctx))
    _, rumor_effects = reduce_rumor_propagation({}, copy.deepcopy(ctx))
    _, location_effects = reduce_location_conditions({}, copy.deepcopy(ctx))
    _, npc_effects = reduce_npc_activities({}, copy.deepcopy(ctx))

    all_effects = faction_effects + rumor_effects + location_effects + npc_effects
    for effect in all_effects:
        assert effect["effect_type"] in SUPPORTED_WORLD_EFFECT_TYPES, (
            f"Unsupported effect_type: {effect['effect_type']}"
        )


def test_advance_emits_only_supported_effect_types() -> None:
    """Full advance() cycle only emits supported effect types."""
    coherence = _MockCoherenceCore(
        threads=[
            {"thread_id": "guild_a_x", "status": "active"},
            {"thread_id": "guild_a_y", "status": "active"},
        ],
        consequences=[{"id": "c1"}, {"id": "c2"}],
    )
    social_state = _MockSocialState(
        alliances={"a1": _MockAlliance("guild_a", "guild_b")},
        rumors={"r1": _MockRumor("r1", active=True)},
        relationships={"rel1": _MockRelationship("guild_a", "guild_b", "hostile")},
    )

    ctrl = WorldSimController()
    result = ctrl.advance(
        coherence_core=coherence,
        social_state_core=_MockSocialStateCore(state=social_state),
        arc_control_controller=_MockArcControlController(),
        campaign_memory_core=_MockCampaignMemoryCore(),
        encounter_controller=_MockEncounterController(
            seed={"mode": "combat", "location": "market"},
        ),
        tick=1,
    )

    for effect in result.generated_effects:
        assert effect["effect_type"] in SUPPORTED_WORLD_EFFECT_TYPES, (
            f"Unsupported effect_type from advance: {effect['effect_type']}"
        )


# ==================================================================
# 5. Bounded recent effects / history
# ==================================================================


def test_recent_effects_bounded_after_many_advances() -> None:
    """state.recent_effects never exceeds _MAX_RECENT_EFFECTS (50)."""
    ctrl = WorldSimController()

    # Use rich inputs that produce effects each tick
    coherence = _MockCoherenceCore(
        threads=[
            {"thread_id": "guild_a_t1", "status": "active"},
            {"thread_id": "guild_a_t2", "status": "active"},
        ],
        consequences=[{"id": "c1"}, {"id": "c2"}, {"id": "c3"}],
        locations=["market", "docks", "tavern"],
        scene_location="market",
    )
    social_state = _MockSocialState(
        alliances={"a1": _MockAlliance("guild_a", "guild_b")},
        rumors={"r1": _MockRumor("r1", active=True, location="tavern")},
        relationships={"rel1": _MockRelationship("guild_a", "guild_b", "hostile")},
    )

    for tick in range(100):
        ctrl.advance(
            coherence_core=coherence,
            social_state_core=_MockSocialStateCore(state=social_state),
            arc_control_controller=_MockArcControlController(),
            campaign_memory_core=_MockCampaignMemoryCore(),
            encounter_controller=_MockEncounterController(),
            tick=tick,
        )
        assert len(ctrl.get_state().recent_effects) <= _MAX_RECENT_EFFECTS, (
            f"recent_effects exceeded bound at tick {tick}: "
            f"{len(ctrl.get_state().recent_effects)}"
        )


def test_recent_effects_trim_preserves_newest() -> None:
    """When trimmed, the most recent effects are kept (not oldest)."""
    ctrl = WorldSimController()

    coherence = _MockCoherenceCore(
        threads=[
            {"thread_id": "guild_a_t1", "status": "active"},
            {"thread_id": "guild_a_t2", "status": "active"},
        ],
        consequences=[{"id": "c1"}, {"id": "c2"}, {"id": "c3"}],
    )
    social_state = _MockSocialState(
        alliances={"a1": _MockAlliance("guild_a", "guild_b")},
        relationships={"rel1": _MockRelationship("guild_a", "guild_b", "hostile")},
    )

    last_tick = None
    for tick in range(100):
        result = ctrl.advance(
            coherence_core=coherence,
            social_state_core=_MockSocialStateCore(state=social_state),
            arc_control_controller=_MockArcControlController(),
            campaign_memory_core=_MockCampaignMemoryCore(),
            encounter_controller=_MockEncounterController(),
            tick=tick,
        )
        last_tick = tick

    # The most recent effects should be from the later portion of ticks.
    # Early-tick effects (tick 0, 1, …) should have been evicted.
    recent = ctrl.get_state().recent_effects
    assert len(recent) <= _MAX_RECENT_EFFECTS
    if len(recent) == _MAX_RECENT_EFFECTS:
        # The very first effect stored should NOT be from tick 0 — it was
        # trimmed away in favour of newer entries.
        first_id = recent[0].get("effect_id", "")
        assert ":0:" not in first_id and not first_id.endswith(":0"), (
            "oldest effects should have been trimmed, but tick-0 effect still present"
        )
