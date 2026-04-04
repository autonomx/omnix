"""Phase 2 — World Graph + Simulation Inspector tests.

Tests cover:
- build_world_graph: node/edge construction for factions, locations, NPCs, threads, opening
- build_simulation_summary: entity counts, hot locations, orphan NPCs, isolated factions, tensions
- build_entity_inspector: per-entity detail maps
- inspect_world: combined top-level entry point
- Service layer: inspect_world through adventure_builder_service
- Route layer: POST /api/rpg/adventure/inspect-world
"""

from __future__ import annotations

import json

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _base_setup():
    """A realistic adventure setup payload for testing."""
    return {
        "setup_id": "adventure_test123",
        "title": "The Night Market Conspiracy",
        "genre": "fantasy",
        "setting": "A sprawling port city ruled by rival factions",
        "premise": "Something sinister lurks beneath the Night Market.",
        "factions": [
            {
                "faction_id": "fac_red_knives",
                "name": "Red Knives",
                "description": "A criminal syndicate controlling the docks.",
                "goals": ["Control smuggling routes", "Eliminate rivals"],
            },
            {
                "faction_id": "fac_merchant_guild",
                "name": "Merchant Guild",
                "description": "A wealthy trade consortium.",
                "goals": ["Maintain trade monopoly"],
            },
            {
                "faction_id": "fac_isolated",
                "name": "Shadow Circle",
                "description": "A secretive faction with no known members.",
                "goals": [],
            },
        ],
        "locations": [
            {
                "location_id": "loc_night_market",
                "name": "Night Market",
                "description": "A bustling market district.",
                "tags": ["market", "crowded", "dangerous"],
            },
            {
                "location_id": "loc_docks",
                "name": "The Docks",
                "description": "Where ships unload cargo.",
                "tags": ["waterfront"],
            },
            {
                "location_id": "loc_empty",
                "name": "Abandoned Tower",
                "description": "No one goes here.",
                "tags": ["ruins"],
            },
        ],
        "npc_seeds": [
            {
                "npc_id": "npc_mara_voss",
                "name": "Mara Voss",
                "role": "Fixer",
                "description": "A cunning negotiator.",
                "goals": ["Make profit", "Stay alive"],
                "faction_id": "fac_red_knives",
                "location_id": "loc_night_market",
            },
            {
                "npc_id": "npc_kael",
                "name": "Kael",
                "role": "Guard Captain",
                "description": "Loyal to the Merchant Guild.",
                "goals": ["Protect the Guild"],
                "faction_id": "fac_merchant_guild",
                "location_id": "loc_docks",
            },
            {
                "npc_id": "npc_orphan_wanderer",
                "name": "Wanderer",
                "role": "Drifter",
                "description": "Has no faction or home.",
                "goals": [],
                "faction_id": "",
                "location_id": "",
            },
        ],
        "starting_location_id": "loc_night_market",
        "starting_npc_ids": ["npc_mara_voss"],
        "metadata": {
            "regenerated_threads": [
                {
                    "thread_id": "thread_smuggling",
                    "title": "Smuggling Operation",
                    "description": "Red Knives are smuggling contraband.",
                    "involved_entities": ["npc_mara_voss"],
                    "faction_ids": ["fac_red_knives", "fac_merchant_guild"],
                    "location_ids": ["loc_night_market", "loc_docks"],
                    "status": "active",
                },
                {
                    "thread_id": "thread_shadow",
                    "title": "Shadow Conspiracy",
                    "description": "Something darker is at play.",
                    "involved_entities": [],
                    "faction_ids": [],
                    "location_ids": [],
                    "status": "active",
                },
            ],
            "regenerated_opening": {
                "opening_text": "You step into the night market...",
                "resolved_context": {
                    "location_id": "loc_night_market",
                    "npc_ids": ["npc_mara_voss"],
                },
            },
        },
        "hard_rules": ["Magic is rare"],
        "soft_tone_rules": ["Dark and gritty"],
        "forbidden_content": [],
        "canon_notes": [],
    }


def _minimal_setup():
    """Bare minimum setup with required fields only."""
    return {
        "setup_id": "adventure_minimal",
        "title": "Minimal",
        "genre": "fantasy",
        "setting": "A village",
        "premise": "Something happened.",
    }


def _empty_setup():
    """Completely empty setup."""
    return {}


# ===========================================================================
# build_world_graph
# ===========================================================================


class TestBuildWorldGraph:
    """Tests for build_world_graph()."""

    def test_faction_nodes(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        faction_nodes = [n for n in result["nodes"] if n["type"] == "faction"]
        assert len(faction_nodes) == 3
        ids = {n["id"] for n in faction_nodes}
        assert "fac_red_knives" in ids
        assert "fac_merchant_guild" in ids

    def test_location_nodes(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        location_nodes = [n for n in result["nodes"] if n["type"] == "location"]
        assert len(location_nodes) == 3

    def test_npc_nodes(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        npc_nodes = [n for n in result["nodes"] if n["type"] == "npc"]
        assert len(npc_nodes) == 3

    def test_thread_nodes(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        thread_nodes = [n for n in result["nodes"] if n["type"] == "thread"]
        assert len(thread_nodes) == 2

    def test_opening_node(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        opening_nodes = [n for n in result["nodes"] if n["type"] == "opening"]
        assert len(opening_nodes) == 1
        assert opening_nodes[0]["label"] == "Opening Scene"

    def test_npc_member_of_edges(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        member_edges = [e for e in result["edges"] if e["type"] == "member_of"]
        assert len(member_edges) == 2
        sources = {e["source"] for e in member_edges}
        assert "npc_mara_voss" in sources
        assert "npc_kael" in sources

    def test_npc_located_in_edges(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        located_edges = [e for e in result["edges"] if e["type"] == "located_in"]
        assert len(located_edges) == 2

    def test_thread_involves_edges(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        involves_edges = [e for e in result["edges"] if e["type"] == "involves"]
        assert len(involves_edges) >= 1  # thread_smuggling → npc_mara_voss + locations

    def test_thread_pressures_edges(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        pressure_edges = [e for e in result["edges"] if e["type"] == "pressures"]
        assert len(pressure_edges) == 2  # thread_smuggling → both factions

    def test_opening_starts_at_edge(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        starts_edges = [e for e in result["edges"] if e["type"] == "starts_at"]
        assert len(starts_edges) == 1
        assert starts_edges[0]["target"] == "loc_night_market"

    def test_opening_connected_to_edges(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        connected_edges = [e for e in result["edges"] if e["type"] == "connected_to"]
        assert len(connected_edges) == 1
        assert connected_edges[0]["target"] == "npc_mara_voss"

    def test_empty_setup(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_empty_setup())
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_minimal_setup(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_minimal_setup())
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_no_opening_without_context(self):
        from app.rpg.creator.world_graph import build_world_graph

        setup = _base_setup()
        setup["starting_location_id"] = None
        setup["starting_npc_ids"] = []
        result = build_world_graph(setup)
        opening_nodes = [n for n in result["nodes"] if n["type"] == "opening"]
        assert len(opening_nodes) == 0

    def test_node_shape(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        node = next(n for n in result["nodes"] if n["id"] == "npc_mara_voss")
        assert node["type"] == "npc"
        assert node["label"] == "Mara Voss"
        assert "meta" in node
        assert node["meta"]["role"] == "Fixer"

    def test_edge_shape(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        edge = next(e for e in result["edges"] if e["source"] == "npc_mara_voss" and e["type"] == "member_of")
        assert edge["target"] == "fac_red_knives"

    def test_orphan_npc_no_edges(self):
        from app.rpg.creator.world_graph import build_world_graph

        result = build_world_graph(_base_setup())
        orphan_edges = [e for e in result["edges"] if e["source"] == "npc_orphan_wanderer" or e["target"] == "npc_orphan_wanderer"]
        assert len(orphan_edges) == 0

    def test_thread_without_id_gets_generated(self):
        from app.rpg.creator.world_graph import build_world_graph

        setup = _minimal_setup()
        setup["metadata"] = {
            "regenerated_threads": [
                {"title": "Unnamed thread", "involved_entities": []},
            ]
        }
        result = build_world_graph(setup)
        thread_nodes = [n for n in result["nodes"] if n["type"] == "thread"]
        assert len(thread_nodes) == 1
        assert thread_nodes[0]["id"] == "thread_0"

    def test_skips_empty_faction_id(self):
        from app.rpg.creator.world_graph import build_world_graph

        setup = _minimal_setup()
        setup["factions"] = [{"faction_id": "", "name": "Nameless"}]
        result = build_world_graph(setup)
        assert len(result["nodes"]) == 0


# ===========================================================================
# build_simulation_summary
# ===========================================================================


class TestBuildSimulationSummary:
    """Tests for build_simulation_summary()."""

    def test_entity_counts(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        result = build_simulation_summary(_base_setup())
        counts = result["entity_counts"]
        assert counts["factions"] == 3
        assert counts["locations"] == 3
        assert counts["npcs"] == 3
        assert counts["threads"] == 2

    def test_hot_locations(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        result = build_simulation_summary(_base_setup())
        hot = result["hot_locations"]
        assert len(hot) >= 1
        # Night Market should be hottest (1 NPC + 1 thread)
        assert hot[0]["location_id"] == "loc_night_market"
        assert hot[0]["npc_count"] == 1
        assert hot[0]["thread_count"] == 1

    def test_isolated_factions(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        result = build_simulation_summary(_base_setup())
        isolated = result["isolated_factions"]
        assert len(isolated) == 1
        assert isolated[0]["faction_id"] == "fac_isolated"

    def test_orphan_npcs(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        result = build_simulation_summary(_base_setup())
        orphans = result["orphan_npcs"]
        assert len(orphans) == 1
        assert orphans[0]["npc_id"] == "npc_orphan_wanderer"

    def test_faction_tensions(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        result = build_simulation_summary(_base_setup())
        tensions = result["faction_tensions"]
        assert len(tensions) >= 1
        # Red Knives and Merchant Guild share a thread
        faction_pair = tensions[0]["factions"]
        assert "fac_red_knives" in faction_pair
        assert "fac_merchant_guild" in faction_pair

    def test_unresolved_threads(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        result = build_simulation_summary(_base_setup())
        unresolved = result["unresolved_threads"]
        assert len(unresolved) == 2  # both active

    def test_resolved_context(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        result = build_simulation_summary(_base_setup())
        ctx = result["resolved_context"]
        assert ctx["location_id"] == "loc_night_market"
        assert "npc_mara_voss" in ctx["npc_ids"]

    def test_empty_setup_counts(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        result = build_simulation_summary(_empty_setup())
        counts = result["entity_counts"]
        assert counts["factions"] == 0
        assert counts["npcs"] == 0
        assert counts["threads"] == 0

    def test_no_threads_no_tensions(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        setup = _base_setup()
        setup["metadata"]["regenerated_threads"] = []
        result = build_simulation_summary(setup)
        assert result["faction_tensions"] == []

    def test_empty_tower_not_hot(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        result = build_simulation_summary(_base_setup())
        hot_ids = {h["location_id"] for h in result["hot_locations"]}
        assert "loc_empty" not in hot_ids

    def test_hot_locations_sorted_by_score(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        result = build_simulation_summary(_base_setup())
        hot = result["hot_locations"]
        scores = [h["score"] for h in hot]
        assert scores == sorted(scores, reverse=True)

    def test_resolved_thread_not_unresolved(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        setup = _base_setup()
        setup["metadata"]["regenerated_threads"][0]["status"] = "resolved"
        result = build_simulation_summary(setup)
        unresolved_ids = {t["thread_id"] for t in result["unresolved_threads"]}
        assert "thread_smuggling" not in unresolved_ids
        assert "thread_shadow" in unresolved_ids


# ===========================================================================
# build_entity_inspector
# ===========================================================================


class TestBuildEntityInspector:
    """Tests for build_entity_inspector()."""

    def test_npc_inspector(self):
        from app.rpg.creator.world_graph import build_entity_inspector

        result = build_entity_inspector(_base_setup())
        entities = result["entities"]
        assert "npc_mara_voss" in entities
        npc = entities["npc_mara_voss"]
        assert npc["type"] == "npc"
        assert npc["name"] == "Mara Voss"
        assert npc["role"] == "Fixer"
        assert npc["faction_id"] == "fac_red_knives"
        assert npc["location_id"] == "loc_night_market"

    def test_npc_related_threads(self):
        from app.rpg.creator.world_graph import build_entity_inspector

        result = build_entity_inspector(_base_setup())
        npc = result["entities"]["npc_mara_voss"]
        assert len(npc["related_threads"]) >= 1
        thread_ids = [t["thread_id"] for t in npc["related_threads"]]
        assert "thread_smuggling" in thread_ids

    def test_faction_inspector(self):
        from app.rpg.creator.world_graph import build_entity_inspector

        result = build_entity_inspector(_base_setup())
        fac = result["entities"]["fac_red_knives"]
        assert fac["type"] == "faction"
        assert fac["name"] == "Red Knives"
        assert len(fac["members"]) == 1
        assert fac["members"][0]["npc_id"] == "npc_mara_voss"

    def test_faction_related_locations(self):
        from app.rpg.creator.world_graph import build_entity_inspector

        result = build_entity_inspector(_base_setup())
        fac = result["entities"]["fac_red_knives"]
        assert "loc_night_market" in fac["related_locations"]

    def test_faction_related_threads(self):
        from app.rpg.creator.world_graph import build_entity_inspector

        result = build_entity_inspector(_base_setup())
        fac = result["entities"]["fac_red_knives"]
        thread_ids = [t["thread_id"] for t in fac["related_threads"]]
        assert "thread_smuggling" in thread_ids

    def test_location_inspector(self):
        from app.rpg.creator.world_graph import build_entity_inspector

        result = build_entity_inspector(_base_setup())
        loc = result["entities"]["loc_night_market"]
        assert loc["type"] == "location"
        assert loc["name"] == "Night Market"
        assert len(loc["residents"]) == 1
        assert loc["residents"][0]["npc_id"] == "npc_mara_voss"

    def test_location_involved_factions(self):
        from app.rpg.creator.world_graph import build_entity_inspector

        result = build_entity_inspector(_base_setup())
        loc = result["entities"]["loc_night_market"]
        assert "fac_red_knives" in loc["involved_factions"]

    def test_location_related_threads(self):
        from app.rpg.creator.world_graph import build_entity_inspector

        result = build_entity_inspector(_base_setup())
        loc = result["entities"]["loc_night_market"]
        thread_ids = [t["thread_id"] for t in loc["related_threads"]]
        assert "thread_smuggling" in thread_ids

    def test_thread_inspector(self):
        from app.rpg.creator.world_graph import build_entity_inspector

        result = build_entity_inspector(_base_setup())
        thread = result["entities"]["thread_smuggling"]
        assert thread["type"] == "thread"
        assert thread["title"] == "Smuggling Operation"
        assert "npc_mara_voss" in thread["involved_entities"]

    def test_empty_setup_no_entities(self):
        from app.rpg.creator.world_graph import build_entity_inspector

        result = build_entity_inspector(_empty_setup())
        assert result["entities"] == {}

    def test_all_entity_types_present(self):
        from app.rpg.creator.world_graph import build_entity_inspector

        result = build_entity_inspector(_base_setup())
        types = {e["type"] for e in result["entities"].values()}
        assert "npc" in types
        assert "faction" in types
        assert "location" in types
        assert "thread" in types


# ===========================================================================
# inspect_world (top-level)
# ===========================================================================


class TestInspectWorld:
    """Tests for the combined inspect_world()."""

    def test_success_flag(self):
        from app.rpg.creator.world_graph import inspect_world

        result = inspect_world(_base_setup())
        assert result["success"] is True

    def test_has_all_sections(self):
        from app.rpg.creator.world_graph import inspect_world

        result = inspect_world(_base_setup())
        assert "graph" in result
        assert "simulation" in result
        assert "inspector" in result

    def test_graph_has_nodes_and_edges(self):
        from app.rpg.creator.world_graph import inspect_world

        result = inspect_world(_base_setup())
        assert len(result["graph"]["nodes"]) > 0
        assert len(result["graph"]["edges"]) > 0

    def test_simulation_has_counts(self):
        from app.rpg.creator.world_graph import inspect_world

        result = inspect_world(_base_setup())
        assert "entity_counts" in result["simulation"]

    def test_inspector_has_entities(self):
        from app.rpg.creator.world_graph import inspect_world

        result = inspect_world(_base_setup())
        assert "entities" in result["inspector"]

    def test_empty_setup(self):
        from app.rpg.creator.world_graph import inspect_world

        result = inspect_world(_empty_setup())
        assert result["success"] is True
        assert result["graph"]["nodes"] == []


# ===========================================================================
# Service layer
# ===========================================================================


class TestInspectWorldService:
    """Tests for adventure_builder_service.inspect_world()."""

    def test_service_returns_success(self):
        from app.rpg.services.adventure_builder_service import inspect_world

        result = inspect_world(_base_setup())
        assert result["success"] is True

    def test_service_applies_defaults(self):
        from app.rpg.services.adventure_builder_service import inspect_world

        result = inspect_world(_minimal_setup())
        assert result["success"] is True
        assert "graph" in result

    def test_service_handles_empty_payload(self):
        from app.rpg.services.adventure_builder_service import inspect_world

        result = inspect_world({})
        assert result["success"] is True


# ===========================================================================
# Route layer
# ===========================================================================


class TestInspectWorldRoute:
    """Tests for POST /api/rpg/adventure/inspect-world."""

    @pytest.fixture(autouse=True)
    def _setup_app(self):
        from flask import Flask
        from app.rpg.creator_routes import creator_bp

        self.app = Flask(__name__)
        self.app.register_blueprint(creator_bp)
        self.client = self.app.test_client()

    def test_missing_json_body(self):
        res = self.client.post("/api/rpg/adventure/inspect-world")
        assert res.status_code == 400
        data = res.get_json()
        assert data["success"] is False

    def test_success_with_setup(self):
        res = self.client.post(
            "/api/rpg/adventure/inspect-world",
            data=json.dumps({"setup": _base_setup()}),
            content_type="application/json",
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert "graph" in data
        assert "simulation" in data
        assert "inspector" in data

    def test_accepts_flat_payload(self):
        """The route also accepts a flat setup payload (without wrapping in 'setup' key)."""
        res = self.client.post(
            "/api/rpg/adventure/inspect-world",
            data=json.dumps(_base_setup()),
            content_type="application/json",
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True

    def test_response_shape_graph(self):
        res = self.client.post(
            "/api/rpg/adventure/inspect-world",
            data=json.dumps({"setup": _base_setup()}),
            content_type="application/json",
        )
        data = res.get_json()
        graph = data["graph"]
        assert isinstance(graph["nodes"], list)
        assert isinstance(graph["edges"], list)
        if graph["nodes"]:
            node = graph["nodes"][0]
            assert "id" in node
            assert "type" in node
            assert "label" in node
            assert "meta" in node

    def test_response_shape_simulation(self):
        res = self.client.post(
            "/api/rpg/adventure/inspect-world",
            data=json.dumps({"setup": _base_setup()}),
            content_type="application/json",
        )
        data = res.get_json()
        sim = data["simulation"]
        assert "entity_counts" in sim
        assert "hot_locations" in sim
        assert "isolated_factions" in sim
        assert "orphan_npcs" in sim
        assert "unresolved_threads" in sim
        assert "faction_tensions" in sim

    def test_response_shape_inspector(self):
        res = self.client.post(
            "/api/rpg/adventure/inspect-world",
            data=json.dumps({"setup": _base_setup()}),
            content_type="application/json",
        )
        data = res.get_json()
        inspector = data["inspector"]
        assert "entities" in inspector
        assert isinstance(inspector["entities"], dict)

    def test_empty_payload(self):
        res = self.client.post(
            "/api/rpg/adventure/inspect-world",
            data=json.dumps({"setup": {}}),
            content_type="application/json",
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True


# ===========================================================================
# Edge cases & regression
# ===========================================================================


class TestWorldGraphEdgeCases:
    """Edge cases and regression tests."""

    def test_npc_with_nonexistent_faction(self):
        from app.rpg.creator.world_graph import build_world_graph

        setup = _minimal_setup()
        setup["npc_seeds"] = [
            {"npc_id": "npc_1", "name": "X", "role": "Y", "description": "",
             "faction_id": "fac_nonexistent", "location_id": ""},
        ]
        result = build_world_graph(setup)
        # NPC node exists, no member_of edge since faction doesn't exist
        npc_nodes = [n for n in result["nodes"] if n["type"] == "npc"]
        assert len(npc_nodes) == 1
        member_edges = [e for e in result["edges"] if e["type"] == "member_of"]
        assert len(member_edges) == 0

    def test_npc_with_nonexistent_location(self):
        from app.rpg.creator.world_graph import build_world_graph

        setup = _minimal_setup()
        setup["npc_seeds"] = [
            {"npc_id": "npc_1", "name": "X", "role": "Y", "description": "",
             "faction_id": "", "location_id": "loc_nonexistent"},
        ]
        result = build_world_graph(setup)
        located_edges = [e for e in result["edges"] if e["type"] == "located_in"]
        assert len(located_edges) == 0

    def test_duplicate_thread_entity_refs(self):
        from app.rpg.creator.world_graph import build_world_graph

        setup = _base_setup()
        setup["metadata"]["regenerated_threads"] = [
            {
                "thread_id": "t1",
                "title": "T1",
                "involved_entities": ["npc_mara_voss", "npc_mara_voss"],
                "faction_ids": [],
                "location_ids": [],
            },
        ]
        result = build_world_graph(setup)
        involves_edges = [e for e in result["edges"] if e["type"] == "involves" and e["source"] == "t1"]
        assert len(involves_edges) == 2  # both refs create edges

    def test_none_values_handled(self):
        from app.rpg.creator.world_graph import build_world_graph

        setup = {
            "factions": [{"faction_id": None, "name": None}],
            "locations": [{"location_id": None}],
            "npc_seeds": [{"npc_id": None}],
        }
        result = build_world_graph(setup)
        assert result["nodes"] == []

    def test_many_npcs_hot_location(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        setup = _minimal_setup()
        setup["locations"] = [
            {"location_id": "loc_a", "name": "A"},
            {"location_id": "loc_b", "name": "B"},
        ]
        setup["npc_seeds"] = [
            {"npc_id": f"npc_{i}", "name": f"NPC {i}", "role": "", "description": "",
             "faction_id": "", "location_id": "loc_a"}
            for i in range(5)
        ]
        result = build_simulation_summary(setup)
        hot = result["hot_locations"]
        assert hot[0]["location_id"] == "loc_a"
        assert hot[0]["npc_count"] == 5

    def test_all_npcs_orphan(self):
        from app.rpg.creator.world_graph import build_simulation_summary

        setup = _minimal_setup()
        setup["npc_seeds"] = [
            {"npc_id": "npc_1", "name": "A", "role": "", "description": "", "faction_id": "", "location_id": ""},
            {"npc_id": "npc_2", "name": "B", "role": "", "description": "", "faction_id": "", "location_id": ""},
        ]
        result = build_simulation_summary(setup)
        assert len(result["orphan_npcs"]) == 2


# ===========================================================================
# Backward compatibility
# ===========================================================================


class TestPhase2BackwardCompatibility:
    """Ensure Phase 2 additions don't break existing Phase 1.x functionality."""

    @pytest.fixture(autouse=True)
    def _setup_app(self):
        from flask import Flask
        from app.rpg.creator_routes import creator_bp

        self.app = Flask(__name__)
        self.app.register_blueprint(creator_bp)
        self.client = self.app.test_client()

    def test_existing_validate_route_still_works(self):
        res = self.client.post(
            "/api/rpg/adventure/validate",
            data=json.dumps(_base_setup()),
            content_type="application/json",
        )
        assert res.status_code == 200

    def test_existing_template_list_route_still_works(self):
        res = self.client.get("/api/rpg/adventure/templates")
        assert res.status_code == 200

    def test_existing_regenerate_route_still_works(self):
        res = self.client.post(
            "/api/rpg/adventure/regenerate",
            data=json.dumps({
                "target": "factions",
                "setup": _base_setup(),
            }),
            content_type="application/json",
        )
        # Should succeed or fail gracefully (not 500 from import errors)
        assert res.status_code in (200, 400)
