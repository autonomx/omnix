"""Phase 3A — World Simulation Engine tests.

Tests cover:
- build_initial_simulation_state: shape, thread/faction/location values
- step_simulation_state: tick increment, state update, history
- compute_simulation_diff: diff shape, change detection
- summarize_simulation_step: summary strings
- Determinism: same input → same output
- History capping at MAX_HISTORY
- Service layer: advance_world_simulation, get_simulation_state
- Route layer: POST /simulate-step, /simulation-state
- Edge cases: empty setups, missing metadata, no threads
"""

from __future__ import annotations

import copy
import json

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _base_setup():
    """A realistic setup payload with threads, factions, locations, NPCs."""
    return {
        "setup_id": "adventure_test_sim",
        "title": "The Night Market Conspiracy",
        "genre": "fantasy",
        "setting": "A sprawling port city ruled by rival factions",
        "premise": "Something sinister lurks beneath the Night Market.",
        "factions": [
            {
                "faction_id": "fac_red_knives",
                "name": "Red Knives",
                "description": "A criminal syndicate.",
                "goals": ["Control smuggling routes"],
            },
            {
                "faction_id": "fac_merchant_guild",
                "name": "Merchant Guild",
                "description": "A wealthy trade consortium.",
                "goals": ["Maintain trade monopoly"],
            },
        ],
        "locations": [
            {
                "location_id": "loc_night_market",
                "name": "Night Market",
                "description": "A bustling market district.",
                "tags": ["market", "crowded"],
            },
            {
                "location_id": "loc_docks",
                "name": "The Docks",
                "description": "Where ships unload cargo.",
                "tags": ["waterfront"],
            },
        ],
        "npc_seeds": [
            {
                "npc_id": "npc_mara",
                "name": "Mara Voss",
                "role": "Fixer",
                "description": "A cunning negotiator.",
                "goals": ["Make profit"],
                "faction_id": "fac_red_knives",
                "location_id": "loc_night_market",
            },
            {
                "npc_id": "npc_kael",
                "name": "Kael",
                "role": "Guard Captain",
                "description": "Loyal to the Guild.",
                "goals": ["Protect the Guild"],
                "faction_id": "fac_merchant_guild",
                "location_id": "loc_docks",
            },
        ],
        "hard_rules": ["Magic is rare"],
        "soft_tone_rules": ["Dark and gritty"],
        "lore_constraints": [],
        "forbidden_content": [],
        "canon_notes": [],
        "themes": [],
        "starting_location_id": "loc_night_market",
        "starting_npc_ids": ["npc_mara"],
        "metadata": {
            "regenerated_threads": [
                {
                    "thread_id": "thread_smuggling",
                    "title": "Smuggling Operation",
                    "description": "Red Knives smuggle contraband.",
                    "involved_entities": ["npc_mara"],
                    "faction_ids": ["fac_red_knives", "fac_merchant_guild"],
                    "location_ids": ["loc_night_market", "loc_docks"],
                    "status": "active",
                },
            ],
        },
    }


def _multi_thread_setup():
    """Setup with multiple threads and more NPCs for richer pressure testing."""
    base = _base_setup()
    base["npc_seeds"].append({
        "npc_id": "npc_lurker",
        "name": "Lurker",
        "role": "Spy",
        "description": "Watches from the shadows.",
        "goals": ["Gather intel"],
        "faction_id": "fac_red_knives",
        "location_id": "loc_night_market",
    })
    base["metadata"]["regenerated_threads"].append({
        "thread_id": "thread_uprising",
        "title": "Uprising",
        "description": "Workers rebel.",
        "involved_entities": [],
        "faction_ids": ["fac_red_knives"],
        "location_ids": ["loc_night_market"],
        "status": "active",
    })
    return base


def _empty_setup():
    """Minimal setup with no threads, factions, locations, or NPCs."""
    return {
        "setup_id": "adventure_empty",
        "title": "Empty World",
        "genre": "fantasy",
        "setting": "Void",
        "premise": "Nothing here.",
        "factions": [],
        "locations": [],
        "npc_seeds": [],
        "metadata": {},
    }


# ---------------------------------------------------------------------------
# Unit Tests — Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    """Test deterministic helper functions."""

    def test_cap_within_bounds(self):
        from app.rpg.creator.world_simulation import _cap
        assert _cap(3) == 3
        assert _cap(0) == 0
        assert _cap(5) == 5

    def test_cap_lower_bound(self):
        from app.rpg.creator.world_simulation import _cap
        assert _cap(-1) == 0
        assert _cap(-100) == 0

    def test_cap_upper_bound(self):
        from app.rpg.creator.world_simulation import _cap
        assert _cap(6) == 5
        assert _cap(100) == 5

    def test_cap_custom_bounds(self):
        from app.rpg.creator.world_simulation import _cap
        assert _cap(3, lo=1, hi=4) == 3
        assert _cap(0, lo=1, hi=4) == 1
        assert _cap(10, lo=1, hi=4) == 4

    def test_thread_status_low(self):
        from app.rpg.creator.world_simulation import _thread_status
        assert _thread_status(0) == "low"
        assert _thread_status(1) == "low"

    def test_thread_status_active(self):
        from app.rpg.creator.world_simulation import _thread_status
        assert _thread_status(2) == "active"
        assert _thread_status(3) == "active"

    def test_thread_status_critical(self):
        from app.rpg.creator.world_simulation import _thread_status
        assert _thread_status(4) == "critical"
        assert _thread_status(5) == "critical"

    def test_faction_status_stable(self):
        from app.rpg.creator.world_simulation import _faction_status
        assert _faction_status(0) == "stable"

    def test_faction_status_watchful(self):
        from app.rpg.creator.world_simulation import _faction_status
        assert _faction_status(1) == "watchful"
        assert _faction_status(2) == "watchful"

    def test_faction_status_strained(self):
        from app.rpg.creator.world_simulation import _faction_status
        assert _faction_status(3) == "strained"
        assert _faction_status(5) == "strained"

    def test_location_status_quiet(self):
        from app.rpg.creator.world_simulation import _location_status
        assert _location_status(0) == "quiet"
        assert _location_status(1) == "quiet"

    def test_location_status_active(self):
        from app.rpg.creator.world_simulation import _location_status
        assert _location_status(2) == "active"
        assert _location_status(3) == "active"

    def test_location_status_hot(self):
        from app.rpg.creator.world_simulation import _location_status
        assert _location_status(4) == "hot"
        assert _location_status(5) == "hot"


# ---------------------------------------------------------------------------
# Unit Tests — build_initial_simulation_state
# ---------------------------------------------------------------------------


class TestBuildInitialSimulationState:
    """Test initial simulation state generation."""

    def test_shape_has_required_keys(self):
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_base_setup())
        assert "tick" in state
        assert "threads" in state
        assert "factions" in state
        assert "locations" in state
        assert "history" in state

    def test_tick_starts_at_zero(self):
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_base_setup())
        assert state["tick"] == 0

    def test_history_starts_empty(self):
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_base_setup())
        assert state["history"] == []

    def test_threads_populated(self):
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_base_setup())
        assert "thread_smuggling" in state["threads"]

    def test_factions_populated(self):
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_base_setup())
        assert "fac_red_knives" in state["factions"]
        assert "fac_merchant_guild" in state["factions"]

    def test_locations_populated(self):
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_base_setup())
        assert "loc_night_market" in state["locations"]
        assert "loc_docks" in state["locations"]

    def test_thread_has_pressure_and_status(self):
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_base_setup())
        thr = state["threads"]["thread_smuggling"]
        assert "pressure" in thr
        assert "status" in thr
        assert isinstance(thr["pressure"], int)
        assert thr["status"] in ("low", "active", "critical")

    def test_faction_has_pressure_and_status(self):
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_base_setup())
        fac = state["factions"]["fac_red_knives"]
        assert "pressure" in fac
        assert "status" in fac
        assert isinstance(fac["pressure"], int)
        assert fac["status"] in ("stable", "watchful", "strained")

    def test_location_has_heat_and_status(self):
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_base_setup())
        loc = state["locations"]["loc_night_market"]
        assert "heat" in loc
        assert "status" in loc
        assert isinstance(loc["heat"], int)
        assert loc["status"] in ("quiet", "active", "hot")

    def test_thread_pressure_connected_to_two_factions(self):
        """Thread connected to 2 factions should have pressure > base (1)."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_base_setup())
        thr = state["threads"]["thread_smuggling"]
        # Base 1 + 1 for connected to 2 factions (beyond 1) = 2
        assert thr["pressure"] >= 2

    def test_location_heat_with_npcs_and_threads(self):
        """Night Market: 1 NPC + 1 thread = heat 2 (active)."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_base_setup())
        loc = state["locations"]["loc_night_market"]
        # 1 NPC (Mara) + 1 thread (smuggling) = heat 2
        assert loc["heat"] >= 2
        assert loc["status"] in ("active", "hot")

    def test_location_heat_with_more_npcs(self):
        """Night Market with 2 NPCs + 2 threads → higher heat."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_multi_thread_setup())
        loc = state["locations"]["loc_night_market"]
        # 2 NPCs (Mara + Lurker) + 2 threads (smuggling + uprising) = heat 4
        assert loc["heat"] >= 4
        assert loc["status"] == "hot"

    def test_faction_pressure_from_active_threads(self):
        """Faction connected to active/critical thread should have pressure > 0."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_base_setup())
        fac = state["factions"]["fac_red_knives"]
        # thread_smuggling is active → fac_red_knives pressure >= 1
        assert fac["pressure"] >= 1

    def test_empty_setup_produces_empty_state(self):
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_empty_setup())
        assert state["tick"] == 0
        assert state["threads"] == {}
        assert state["factions"] == {}
        assert state["locations"] == {}

    def test_pressure_capped_at_five(self):
        """All pressures and heats must be ≤ 5."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(_multi_thread_setup())
        for thr in state["threads"].values():
            assert thr["pressure"] <= 5
        for fac in state["factions"].values():
            assert fac["pressure"] <= 5
        for loc in state["locations"].values():
            assert loc["heat"] <= 5

    def test_no_metadata_key(self):
        """Setup with no metadata key at all should not crash."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        setup = {"setup_id": "test", "factions": [], "locations": [], "npc_seeds": []}
        state = build_initial_simulation_state(setup)
        assert state["tick"] == 0

    def test_none_payload(self):
        """Passing None should not crash."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        state = build_initial_simulation_state(None)
        assert state["tick"] == 0


# ---------------------------------------------------------------------------
# Unit Tests — step_simulation_state
# ---------------------------------------------------------------------------


class TestStepSimulationState:
    """Test single-step simulation advancement."""

    def test_returns_required_keys(self):
        from app.rpg.creator.world_simulation import step_simulation_state
        result = step_simulation_state(_base_setup())
        assert "next_setup" in result
        assert "before_state" in result
        assert "after_state" in result

    def test_tick_increments(self):
        from app.rpg.creator.world_simulation import step_simulation_state
        result = step_simulation_state(_base_setup())
        assert result["before_state"]["tick"] == 0
        assert result["after_state"]["tick"] == 1

    def test_next_setup_has_simulation_state(self):
        from app.rpg.creator.world_simulation import step_simulation_state
        result = step_simulation_state(_base_setup())
        meta = result["next_setup"].get("metadata", {})
        assert "simulation_state" in meta
        assert meta["simulation_state"]["tick"] == 1

    def test_history_populated_after_step(self):
        from app.rpg.creator.world_simulation import step_simulation_state
        result = step_simulation_state(_base_setup())
        history = result["after_state"]["history"]
        assert len(history) >= 1
        assert history[-1]["tick"] == 1

    def test_does_not_mutate_original(self):
        from app.rpg.creator.world_simulation import step_simulation_state
        original = _base_setup()
        original_copy = copy.deepcopy(original)
        step_simulation_state(original)
        assert original == original_copy

    def test_sequential_ticks(self):
        """Stepping twice should produce tick 1 then tick 2."""
        from app.rpg.creator.world_simulation import step_simulation_state
        r1 = step_simulation_state(_base_setup())
        r2 = step_simulation_state(r1["next_setup"])
        assert r2["before_state"]["tick"] == 1
        assert r2["after_state"]["tick"] == 2

    def test_initializes_missing_simulation_state(self):
        """If metadata has no simulation_state, it initializes one."""
        from app.rpg.creator.world_simulation import step_simulation_state
        setup = _base_setup()
        setup["metadata"].pop("simulation_state", None)
        result = step_simulation_state(setup)
        assert result["before_state"]["tick"] == 0
        assert result["after_state"]["tick"] == 1

    def test_empty_setup_step(self):
        from app.rpg.creator.world_simulation import step_simulation_state
        result = step_simulation_state(_empty_setup())
        assert result["after_state"]["tick"] == 1


# ---------------------------------------------------------------------------
# Unit Tests — compute_simulation_diff
# ---------------------------------------------------------------------------


class TestComputeSimulationDiff:
    """Test diff computation between two simulation states."""

    def test_diff_shape(self):
        from app.rpg.creator.world_simulation import compute_simulation_diff
        diff = compute_simulation_diff(
            {"tick": 0, "threads": {}, "factions": {}, "locations": {}},
            {"tick": 1, "threads": {}, "factions": {}, "locations": {}},
        )
        assert "tick_before" in diff
        assert "tick_after" in diff
        assert "threads_changed" in diff
        assert "factions_changed" in diff
        assert "locations_changed" in diff

    def test_no_changes_empty(self):
        from app.rpg.creator.world_simulation import compute_simulation_diff
        state = {"tick": 0, "threads": {"t1": {"pressure": 2}}, "factions": {}, "locations": {}}
        diff = compute_simulation_diff(state, state)
        assert diff["threads_changed"] == []

    def test_detects_thread_change(self):
        from app.rpg.creator.world_simulation import compute_simulation_diff
        before = {"tick": 0, "threads": {"t1": {"pressure": 1}}, "factions": {}, "locations": {}}
        after = {"tick": 1, "threads": {"t1": {"pressure": 3}}, "factions": {}, "locations": {}}
        diff = compute_simulation_diff(before, after)
        assert len(diff["threads_changed"]) == 1
        assert diff["threads_changed"][0]["id"] == "t1"
        assert diff["threads_changed"][0]["before"]["pressure"] == 1
        assert diff["threads_changed"][0]["after"]["pressure"] == 3

    def test_detects_location_heat_change(self):
        from app.rpg.creator.world_simulation import compute_simulation_diff
        before = {"tick": 0, "threads": {}, "factions": {}, "locations": {"l1": {"heat": 1}}}
        after = {"tick": 1, "threads": {}, "factions": {}, "locations": {"l1": {"heat": 4}}}
        diff = compute_simulation_diff(before, after)
        assert len(diff["locations_changed"]) == 1

    def test_detects_faction_change(self):
        from app.rpg.creator.world_simulation import compute_simulation_diff
        before = {"tick": 0, "threads": {}, "factions": {"f1": {"pressure": 0}}, "locations": {}}
        after = {"tick": 1, "threads": {}, "factions": {"f1": {"pressure": 2}}, "locations": {}}
        diff = compute_simulation_diff(before, after)
        assert len(diff["factions_changed"]) == 1

    def test_empty_states_diff(self):
        from app.rpg.creator.world_simulation import compute_simulation_diff
        diff = compute_simulation_diff({}, {})
        assert diff["threads_changed"] == []
        assert diff["factions_changed"] == []
        assert diff["locations_changed"] == []


# ---------------------------------------------------------------------------
# Unit Tests — summarize_simulation_step
# ---------------------------------------------------------------------------


class TestSummarizeSimulationStep:
    """Test human-readable summary generation."""

    def test_empty_diff_returns_empty_summary(self):
        from app.rpg.creator.world_simulation import summarize_simulation_step
        summary = summarize_simulation_step({
            "threads_changed": [],
            "factions_changed": [],
            "locations_changed": [],
        })
        assert summary == []

    def test_thread_escalation_summary(self):
        from app.rpg.creator.world_simulation import summarize_simulation_step
        summary = summarize_simulation_step({
            "threads_changed": [
                {"id": "t1", "before": {"pressure": 1}, "after": {"pressure": 3}},
            ],
            "factions_changed": [],
            "locations_changed": [],
        })
        assert any("escalated" in line for line in summary)

    def test_thread_deescalation_summary(self):
        from app.rpg.creator.world_simulation import summarize_simulation_step
        summary = summarize_simulation_step({
            "threads_changed": [
                {"id": "t1", "before": {"pressure": 3}, "after": {"pressure": 1}},
            ],
            "factions_changed": [],
            "locations_changed": [],
        })
        assert any("de-escalated" in line for line in summary)

    def test_faction_summary(self):
        from app.rpg.creator.world_simulation import summarize_simulation_step
        summary = summarize_simulation_step({
            "threads_changed": [],
            "factions_changed": [
                {"id": "f1", "before": {"pressure": 0}, "after": {"pressure": 2}},
            ],
            "locations_changed": [],
        })
        assert any("faction" in line for line in summary)

    def test_location_summary(self):
        from app.rpg.creator.world_simulation import summarize_simulation_step
        summary = summarize_simulation_step({
            "threads_changed": [],
            "factions_changed": [],
            "locations_changed": [
                {"id": "l1", "before": {"heat": 1}, "after": {"heat": 4}},
            ],
        })
        assert any("location" in line for line in summary)

    def test_summary_strings_populated(self):
        """Summary should contain human-readable strings."""
        from app.rpg.creator.world_simulation import summarize_simulation_step
        summary = summarize_simulation_step({
            "threads_changed": [
                {"id": "t1", "before": {"pressure": 1}, "after": {"pressure": 3}},
                {"id": "t2", "before": {"pressure": 2}, "after": {"pressure": 4}},
            ],
            "factions_changed": [
                {"id": "f1", "before": {"pressure": 0}, "after": {"pressure": 3}},
            ],
            "locations_changed": [
                {"id": "l1", "before": {"heat": 1}, "after": {"heat": 4}},
            ],
        })
        assert len(summary) >= 3
        for line in summary:
            assert isinstance(line, str)
            assert len(line) > 0


# ---------------------------------------------------------------------------
# Unit Tests — Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Same input must always produce the same output."""

    def test_initial_state_deterministic(self):
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        setup = _base_setup()
        s1 = build_initial_simulation_state(copy.deepcopy(setup))
        s2 = build_initial_simulation_state(copy.deepcopy(setup))
        assert s1 == s2

    def test_step_deterministic(self):
        from app.rpg.creator.world_simulation import step_simulation_state
        setup = _base_setup()
        r1 = step_simulation_state(copy.deepcopy(setup))
        r2 = step_simulation_state(copy.deepcopy(setup))
        assert r1["after_state"] == r2["after_state"]

    def test_diff_deterministic(self):
        from app.rpg.creator.world_simulation import (
            compute_simulation_diff,
            step_simulation_state,
        )
        setup = _base_setup()
        r = step_simulation_state(copy.deepcopy(setup))
        d1 = compute_simulation_diff(r["before_state"], r["after_state"])
        d2 = compute_simulation_diff(r["before_state"], r["after_state"])
        assert d1 == d2

    def test_multi_step_deterministic(self):
        from app.rpg.creator.world_simulation import step_simulation_state
        setup = _base_setup()
        r1 = step_simulation_state(copy.deepcopy(setup))
        r1b = step_simulation_state(r1["next_setup"])
        r2 = step_simulation_state(copy.deepcopy(setup))
        r2b = step_simulation_state(r2["next_setup"])
        assert r1b["after_state"] == r2b["after_state"]


# ---------------------------------------------------------------------------
# Unit Tests — History cap
# ---------------------------------------------------------------------------


class TestHistoryCap:
    """History should be capped at MAX_HISTORY (20)."""

    def test_history_capped(self):
        from app.rpg.creator.world_simulation import step_simulation_state, MAX_HISTORY
        setup = _base_setup()
        current = copy.deepcopy(setup)
        for _ in range(MAX_HISTORY + 5):
            result = step_simulation_state(current)
            current = result["next_setup"]
        final_history = result["after_state"]["history"]
        assert len(final_history) <= MAX_HISTORY


# ---------------------------------------------------------------------------
# Unit Tests — Thread pressure with hot location boost
# ---------------------------------------------------------------------------


class TestThreadHotLocationBoost:
    """Thread connected to a hot location gets +1 pressure."""

    def test_hot_location_boosts_thread(self):
        """Multi-thread setup makes Night Market hot → thread gets +1."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        setup = _multi_thread_setup()
        state = build_initial_simulation_state(setup)
        # Night Market should be hot (heat >= 4)
        nm = state["locations"]["loc_night_market"]
        assert nm["status"] == "hot"
        # thread_smuggling connects to Night Market → should get +1 for hot location
        thr = state["threads"]["thread_smuggling"]
        # base 1 + 1 (2 factions beyond 1) + 1 (hot location) = 3
        assert thr["pressure"] >= 3

    def test_faction_strained_from_critical_threads(self):
        """Faction connected to critical thread should have high pressure."""
        from app.rpg.creator.world_simulation import build_initial_simulation_state
        # Create setup where a thread hits critical (4+)
        setup = _multi_thread_setup()
        # Add more factions to thread to boost pressure
        setup["factions"].append({
            "faction_id": "fac_thieves",
            "name": "Thieves Guild",
            "description": "Thieves.",
            "goals": ["Steal"],
        })
        setup["factions"].append({
            "faction_id": "fac_nobles",
            "name": "Nobles",
            "description": "Aristocrats.",
            "goals": ["Rule"],
        })
        setup["metadata"]["regenerated_threads"][0]["faction_ids"].extend(
            ["fac_thieves", "fac_nobles"]
        )
        state = build_initial_simulation_state(setup)
        thr = state["threads"]["thread_smuggling"]
        # base 1 + 3 (4 factions beyond 1) + possible hot = capped at 5
        assert thr["pressure"] >= 4
        assert thr["status"] == "critical"


# ---------------------------------------------------------------------------
# Service layer tests
# ---------------------------------------------------------------------------


class TestServiceAdvanceWorldSimulation:
    """Test adventure_builder_service.advance_world_simulation."""

    def test_advance_returns_success(self):
        from app.rpg.services.adventure_builder_service import advance_world_simulation
        result = advance_world_simulation(_base_setup())
        assert result["success"] is True

    def test_advance_returns_all_keys(self):
        from app.rpg.services.adventure_builder_service import advance_world_simulation
        result = advance_world_simulation(_base_setup())
        assert "updated_setup" in result
        assert "simulation_state" in result
        assert "simulation_diff" in result
        assert "summary" in result
        assert "graph" in result
        assert "simulation" in result
        assert "inspector" in result
        assert "incident_diff" in result
        assert "reaction_diff" in result

    def test_advance_increments_tick(self):
        from app.rpg.services.adventure_builder_service import advance_world_simulation
        result = advance_world_simulation(_base_setup())
        assert result["simulation_state"]["tick"] == 1

    def test_advance_updated_setup_metadata(self):
        from app.rpg.services.adventure_builder_service import advance_world_simulation
        result = advance_world_simulation(_base_setup())
        meta = result["updated_setup"].get("metadata", {})
        assert "simulation_state" in meta

    def test_advance_diff_populated(self):
        from app.rpg.services.adventure_builder_service import advance_world_simulation
        result = advance_world_simulation(_base_setup())
        diff = result["simulation_diff"]
        assert "tick_before" in diff
        assert "tick_after" in diff


class TestServiceGetSimulationState:
    """Test adventure_builder_service.get_simulation_state."""

    def test_get_returns_success(self):
        from app.rpg.services.adventure_builder_service import get_simulation_state
        result = get_simulation_state(_base_setup())
        assert result["success"] is True

    def test_get_returns_state(self):
        from app.rpg.services.adventure_builder_service import get_simulation_state
        result = get_simulation_state(_base_setup())
        assert "simulation_state" in result
        assert result["simulation_state"]["tick"] == 0

    def test_get_existing_state(self):
        """If metadata already has simulation_state, it returns it."""
        from app.rpg.services.adventure_builder_service import get_simulation_state
        setup = _base_setup()
        setup["metadata"]["simulation_state"] = {
            "tick": 5,
            "threads": {},
            "factions": {},
            "locations": {},
            "history": [],
        }
        result = get_simulation_state(setup)
        assert result["simulation_state"]["tick"] == 5

    def test_get_empty_setup(self):
        from app.rpg.services.adventure_builder_service import get_simulation_state
        result = get_simulation_state(_empty_setup())
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------


def _create_test_app():
    """Create a minimal Flask app with the creator blueprint."""
    from flask import Flask
    from app.rpg.creator_routes import creator_bp

    app = Flask(__name__)
    app.register_blueprint(creator_bp)
    app.config["TESTING"] = True
    return app


class TestSimulateStepRoute:
    """Test POST /api/rpg/adventure/simulate-step."""

    def test_simulate_step_success(self):
        app = _create_test_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/rpg/adventure/simulate-step",
                data=json.dumps({"setup": _base_setup()}),
                content_type="application/json",
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["simulation_state"]["tick"] == 1

    def test_simulate_step_missing_body(self):
        app = _create_test_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/rpg/adventure/simulate-step",
                content_type="application/json",
            )
            assert resp.status_code == 400

    def test_simulate_step_empty_setup(self):
        app = _create_test_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/rpg/adventure/simulate-step",
                data=json.dumps({"setup": _empty_setup()}),
                content_type="application/json",
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True

    def test_simulate_step_returns_graph(self):
        app = _create_test_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/rpg/adventure/simulate-step",
                data=json.dumps({"setup": _base_setup()}),
                content_type="application/json",
            )
            data = resp.get_json()
            assert "graph" in data
            assert "simulation" in data
            assert "inspector" in data


class TestSimulationStateRoute:
    """Test POST /api/rpg/adventure/simulation-state."""

    def test_simulation_state_success(self):
        app = _create_test_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/rpg/adventure/simulation-state",
                data=json.dumps({"setup": _base_setup()}),
                content_type="application/json",
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert "simulation_state" in data

    def test_simulation_state_missing_body(self):
        app = _create_test_app()
        with app.test_client() as client:
            resp = client.post(
                "/api/rpg/adventure/simulation-state",
                content_type="application/json",
            )
            assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Integration — Full step cycle
# ---------------------------------------------------------------------------


class TestFullStepCycle:
    """End-to-end: step multiple times and verify progression."""

    def test_three_step_progression(self):
        from app.rpg.creator.world_simulation import step_simulation_state
        setup = _base_setup()
        current = copy.deepcopy(setup)
        for expected_tick in (1, 2, 3):
            result = step_simulation_state(current)
            assert result["after_state"]["tick"] == expected_tick
            assert len(result["after_state"]["history"]) == expected_tick
            current = result["next_setup"]

    def test_step_preserves_setup_shape(self):
        """next_setup should still look like a valid setup payload."""
        from app.rpg.creator.world_simulation import step_simulation_state
        result = step_simulation_state(_base_setup())
        ns = result["next_setup"]
        assert "setup_id" in ns
        assert "factions" in ns
        assert "locations" in ns
        assert "npc_seeds" in ns
        assert "metadata" in ns
