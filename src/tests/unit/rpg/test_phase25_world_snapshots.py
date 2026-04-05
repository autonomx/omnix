"""Phase 2.5 — World Snapshot + Graph Diff tests.

Tests cover:
- build_world_snapshot: snapshot wrapper shape
- compute_graph_diff: node added/removed/changed, edge added/removed
- compute_entity_history_diff: entity field diffs, existence checks
- summarize_graph_diff: human-readable summary strings
- Service layer: inspect_world_snapshot, compare_world, compare_world_entity
- Route layer: POST /inspect-world-snapshot, /compare-world, /compare-entity
- Determinism: stable diff output with ordering changes
"""

from __future__ import annotations

import copy
import json

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _base_setup():
    """A realistic adventure setup payload for snapshot testing."""
    return {
        "setup_id": "adventure_test_snap",
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


def _modified_setup():
    """Base setup with changes: add an NPC, remove a faction, change a location."""
    setup = _base_setup()
    # Add a new NPC
    setup["npc_seeds"].append({
        "npc_id": "npc_new_spy",
        "name": "Shadow Spy",
        "role": "Informant",
        "description": "Works for no one.",
        "goals": ["Gather intel"],
        "faction_id": "",
        "location_id": "loc_night_market",
    })
    # Remove Merchant Guild faction
    setup["factions"] = [f for f in setup["factions"] if f["faction_id"] != "fac_merchant_guild"]
    # Change Night Market tags
    for loc in setup["locations"]:
        if loc["location_id"] == "loc_night_market":
            loc["tags"] = ["market", "crowded", "dangerous", "haunted"]
    return setup


# ===========================================================================
# build_world_snapshot
# ===========================================================================


class TestBuildWorldSnapshot:
    """Tests for build_world_snapshot()."""

    def test_snapshot_has_required_keys(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot
        snap = build_world_snapshot(_base_setup())
        assert "snapshot_id" in snap
        assert "label" in snap
        assert "created_at" in snap
        assert "graph" in snap
        assert "simulation" in snap
        assert "inspector" in snap
        assert "summary" in snap

    def test_snapshot_id_is_string(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot
        snap = build_world_snapshot(_base_setup())
        assert isinstance(snap["snapshot_id"], str)
        assert snap["snapshot_id"].startswith("snap_")

    def test_snapshot_label_default(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot
        snap = build_world_snapshot(_base_setup())
        assert snap["label"] == "Snapshot"

    def test_snapshot_label_custom(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot
        snap = build_world_snapshot(_base_setup(), label="After NPC Regen")
        assert snap["label"] == "After NPC Regen"

    def test_snapshot_created_at_is_float(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot
        snap = build_world_snapshot(_base_setup())
        assert isinstance(snap["created_at"], float)

    def test_snapshot_summary_counts(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot
        snap = build_world_snapshot(_base_setup())
        assert snap["summary"]["node_count"] > 0
        assert snap["summary"]["edge_count"] > 0

    def test_snapshot_graph_has_nodes_and_edges(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot
        snap = build_world_snapshot(_base_setup())
        assert "nodes" in snap["graph"]
        assert "edges" in snap["graph"]

    def test_snapshot_inspector_has_entities(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot
        snap = build_world_snapshot(_base_setup())
        assert "entities" in snap["inspector"]

    def test_snapshot_has_content_hash(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot
        snap = build_world_snapshot(_base_setup())
        assert "content_hash" in snap
        assert isinstance(snap["content_hash"], str)

    def test_snapshot_id_is_stable_for_identical_setup(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot
        setup = _base_setup()
        snap1 = build_world_snapshot(setup, label="A")
        snap2 = build_world_snapshot(setup, label="B")
        assert snap1["content_hash"] == snap2["content_hash"]
        assert snap1["snapshot_id"] == snap2["snapshot_id"]

    def test_snapshot_ids_are_unique(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot
        snap1 = build_world_snapshot(_base_setup())
        setup2 = _base_setup()
        setup2["title"] = "Different Title"
        snap2 = build_world_snapshot(setup2)
        assert snap1["snapshot_id"] != snap2["snapshot_id"]

    def test_empty_setup(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot
        snap = build_world_snapshot({})
        assert snap["summary"]["node_count"] == 0
        assert snap["summary"]["edge_count"] == 0


# ===========================================================================
# compute_graph_diff — Node diff
# ===========================================================================


class TestComputeGraphDiffNodes:
    """Tests for node diffing in compute_graph_diff()."""

    def test_identical_graphs_no_diff(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_graph_diff
        snap = build_world_snapshot(_base_setup())
        diff = compute_graph_diff(snap["graph"], snap["graph"])
        assert diff["nodes"]["added"] == []
        assert diff["nodes"]["removed"] == []
        assert diff["nodes"]["changed"] == []

    def test_added_node(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_graph_diff
        before = build_world_snapshot(_base_setup())
        after = build_world_snapshot(_modified_setup())
        diff = compute_graph_diff(before["graph"], after["graph"])
        assert "npc_new_spy" in diff["nodes"]["added"]

    def test_removed_node(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_graph_diff
        before = build_world_snapshot(_base_setup())
        after = build_world_snapshot(_modified_setup())
        diff = compute_graph_diff(before["graph"], after["graph"])
        assert "fac_merchant_guild" in diff["nodes"]["removed"]

    def test_changed_node(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_graph_diff
        before = build_world_snapshot(_base_setup())
        after = build_world_snapshot(_modified_setup())
        diff = compute_graph_diff(before["graph"], after["graph"])
        changed_ids = [c["id"] for c in diff["nodes"]["changed"]]
        assert "loc_night_market" in changed_ids

    def test_changed_fields_are_listed(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_graph_diff
        before = build_world_snapshot(_base_setup())
        after = build_world_snapshot(_modified_setup())
        diff = compute_graph_diff(before["graph"], after["graph"])
        for c in diff["nodes"]["changed"]:
            if c["id"] == "loc_night_market":
                assert "meta" in c["fields"]
                break
        else:
            pytest.fail("loc_night_market not in changed nodes")

    def test_none_before_graph(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_graph_diff
        after = build_world_snapshot(_base_setup())
        diff = compute_graph_diff(None, after["graph"])
        assert len(diff["nodes"]["added"]) > 0
        assert diff["nodes"]["removed"] == []

    def test_none_after_graph(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_graph_diff
        before = build_world_snapshot(_base_setup())
        diff = compute_graph_diff(before["graph"], None)
        assert diff["nodes"]["added"] == []
        assert len(diff["nodes"]["removed"]) > 0

    def test_both_none(self):
        from app.rpg.creator.world_snapshot import compute_graph_diff
        diff = compute_graph_diff(None, None)
        assert diff["nodes"]["added"] == []
        assert diff["nodes"]["removed"] == []
        assert diff["nodes"]["changed"] == []

    def test_label_change_detected(self):
        from app.rpg.creator.world_snapshot import compute_graph_diff
        before = {"nodes": [{"id": "a", "type": "npc", "label": "Old", "meta": {}}], "edges": []}
        after = {"nodes": [{"id": "a", "type": "npc", "label": "New", "meta": {}}], "edges": []}
        diff = compute_graph_diff(before, after)
        assert len(diff["nodes"]["changed"]) == 1
        assert "label" in diff["nodes"]["changed"][0]["fields"]

    def test_type_change_detected(self):
        from app.rpg.creator.world_snapshot import compute_graph_diff
        before = {"nodes": [{"id": "a", "type": "npc", "label": "X", "meta": {}}], "edges": []}
        after = {"nodes": [{"id": "a", "type": "faction", "label": "X", "meta": {}}], "edges": []}
        diff = compute_graph_diff(before, after)
        assert len(diff["nodes"]["changed"]) == 1
        assert "type" in diff["nodes"]["changed"][0]["fields"]


# ===========================================================================
# compute_graph_diff — Edge diff
# ===========================================================================


class TestComputeGraphDiffEdges:
    """Tests for edge diffing in compute_graph_diff()."""

    def test_identical_graphs_no_edge_diff(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_graph_diff
        snap = build_world_snapshot(_base_setup())
        diff = compute_graph_diff(snap["graph"], snap["graph"])
        assert diff["edges"]["added"] == []
        assert diff["edges"]["removed"] == []

    def test_added_edge(self):
        from app.rpg.creator.world_snapshot import compute_graph_diff
        before = {"nodes": [], "edges": []}
        after = {"nodes": [], "edges": [{"source": "a", "target": "b", "type": "x"}]}
        diff = compute_graph_diff(before, after)
        assert len(diff["edges"]["added"]) == 1
        assert diff["edges"]["added"][0]["source"] == "a"

    def test_removed_edge(self):
        from app.rpg.creator.world_snapshot import compute_graph_diff
        before = {"nodes": [], "edges": [{"source": "a", "target": "b", "type": "x"}]}
        after = {"nodes": [], "edges": []}
        diff = compute_graph_diff(before, after)
        assert len(diff["edges"]["removed"]) == 1
        assert diff["edges"]["removed"][0]["source"] == "a"

    def test_removing_faction_removes_dependent_edge(self):
        """Removing a faction should also remove edges pointing to it."""
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_graph_diff
        before = build_world_snapshot(_base_setup())
        after = build_world_snapshot(_modified_setup())
        diff = compute_graph_diff(before["graph"], after["graph"])
        removed_targets = {e["target"] for e in diff["edges"]["removed"]}
        assert "fac_merchant_guild" in removed_targets

    def test_adding_npc_creates_edges(self):
        """Adding an NPC at a known location should create location edge."""
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_graph_diff
        before = build_world_snapshot(_base_setup())
        after = build_world_snapshot(_modified_setup())
        diff = compute_graph_diff(before["graph"], after["graph"])
        added_sources = {e["source"] for e in diff["edges"]["added"]}
        assert "npc_new_spy" in added_sources

    def test_edge_identity_is_tuple(self):
        """Same source/target/type should not appear as added and removed."""
        from app.rpg.creator.world_snapshot import compute_graph_diff
        edge = {"source": "a", "target": "b", "type": "x"}
        graph = {"nodes": [], "edges": [edge]}
        diff = compute_graph_diff(graph, graph)
        assert diff["edges"]["added"] == []
        assert diff["edges"]["removed"] == []

    def test_compute_graph_diff_dedupes_and_normalizes_edges(self):
        from app.rpg.creator.world_snapshot import compute_graph_diff

        before = {
            "nodes": [],
            "edges": [
                {"source": "a", "target": "b", "type": "member_of"},
                {"source": "a", "target": "b", "type": "member_of"},
            ],
        }
        after = {
            "nodes": [],
            "edges": [
                {"source": "a", "target": "b", "type": "member_of"},
                {"source": "b", "target": "c", "type": "connected_to"},
            ],
        }
        diff = compute_graph_diff(before, after)
        assert diff["edges"]["removed"] == []
        assert len(diff["edges"]["added"]) == 1
        assert diff["edges"]["added"][0]["source"] == "b"
        assert diff["edges"]["added"][0]["target"] == "c"


# ===========================================================================
# compute_graph_diff — Summary
# ===========================================================================


class TestSummarizeGraphDiff:
    """Tests for summarize_graph_diff()."""

    def test_empty_diff_no_summary(self):
        from app.rpg.creator.world_snapshot import compute_graph_diff
        diff = compute_graph_diff(None, None)
        assert diff["summary"] == []

    def test_summary_strings_format(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_graph_diff
        before = build_world_snapshot(_base_setup())
        after = build_world_snapshot(_modified_setup())
        diff = compute_graph_diff(before["graph"], after["graph"])
        assert len(diff["summary"]) > 0
        for s in diff["summary"]:
            assert isinstance(s, str)

    def test_single_node_uses_singular(self):
        from app.rpg.creator.world_snapshot import summarize_graph_diff
        lines = summarize_graph_diff(["a"], [], [], [], [])
        assert lines == ["1 node added"]

    def test_multiple_nodes_uses_plural(self):
        from app.rpg.creator.world_snapshot import summarize_graph_diff
        lines = summarize_graph_diff(["a", "b"], [], [], [], [])
        assert lines == ["2 nodes added"]


# ===========================================================================
# compute_entity_history_diff
# ===========================================================================


class TestComputeEntityHistoryDiff:
    """Tests for compute_entity_history_diff()."""

    def test_entity_not_in_either(self):
        from app.rpg.creator.world_snapshot import compute_entity_history_diff
        result = compute_entity_history_diff(
            {"entities": {}}, {"entities": {}}, "npc_ghost"
        )
        assert result["exists_before"] is False
        assert result["exists_after"] is False
        assert result["changed_fields"] == []

    def test_entity_added(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_entity_history_diff
        before = build_world_snapshot(_base_setup())
        after = build_world_snapshot(_modified_setup())
        result = compute_entity_history_diff(
            before["inspector"], after["inspector"], "npc_new_spy"
        )
        assert result["exists_before"] is False
        assert result["exists_after"] is True

    def test_entity_removed(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_entity_history_diff
        before = build_world_snapshot(_base_setup())
        after = build_world_snapshot(_modified_setup())
        result = compute_entity_history_diff(
            before["inspector"], after["inspector"], "fac_merchant_guild"
        )
        assert result["exists_before"] is True
        assert result["exists_after"] is False

    def test_entity_changed_fields(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_entity_history_diff
        before = build_world_snapshot(_base_setup())
        after = build_world_snapshot(_modified_setup())
        result = compute_entity_history_diff(
            before["inspector"], after["inspector"], "loc_night_market"
        )
        assert result["exists_before"] is True
        assert result["exists_after"] is True
        assert "tags" in result["changed_fields"]

    def test_entity_unchanged(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_entity_history_diff
        snap = build_world_snapshot(_base_setup())
        result = compute_entity_history_diff(
            snap["inspector"], snap["inspector"], "npc_mara_voss"
        )
        assert result["exists_before"] is True
        assert result["exists_after"] is True
        assert result["changed_fields"] == []

    def test_entity_before_and_after_populated(self):
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_entity_history_diff
        before = build_world_snapshot(_base_setup())
        after = build_world_snapshot(_modified_setup())
        result = compute_entity_history_diff(
            before["inspector"], after["inspector"], "loc_night_market"
        )
        assert "before" in result
        assert "after" in result
        assert result["before"]["type"] == "location"

    def test_changing_npc_role_marks_changed(self):
        """Changing NPC role should appear as a changed field."""
        from app.rpg.creator.world_snapshot import compute_entity_history_diff
        before = {"entities": {"npc_a": {"details": {"type": "npc", "role": "Guard", "name": "A"}}}}
        after = {"entities": {"npc_a": {"details": {"type": "npc", "role": "Assassin", "name": "A"}}}}
        result = compute_entity_history_diff(before, after, "npc_a")
        assert "role" in result["changed_fields"]

    def test_related_added(self):
        from app.rpg.creator.world_snapshot import compute_entity_history_diff
        before = {"entities": {"npc_a": {"details": {"type": "npc"}, "related_ids": []}}}
        after = {"entities": {"npc_a": {"details": {"type": "npc"}, "related_ids": ["t1"]}}}
        result = compute_entity_history_diff(before, after, "npc_a")
        assert "t1" in result["related_added"]

    def test_related_removed(self):
        from app.rpg.creator.world_snapshot import compute_entity_history_diff
        before = {"entities": {"npc_a": {"details": {"type": "npc"}, "related_ids": ["t1"]}}}
        after = {"entities": {"npc_a": {"details": {"type": "npc"}, "related_ids": []}}}
        result = compute_entity_history_diff(before, after, "npc_a")
        assert "t1" in result["related_removed"]

    def test_compute_entity_history_diff_list_aware_field_diffs(self):
        from app.rpg.creator.world_snapshot import compute_entity_history_diff

        before_inspector = {
            "entities": {
                "npc_a": {
                    "details": {"goals": ["control market"]},
                    "related_ids": [],
                }
            }
        }
        after_inspector = {
            "entities": {
                "npc_a": {
                    "details": {"goals": ["control market", "expand territory"]},
                    "related_ids": [],
                }
            }
        }
        diff = compute_entity_history_diff(before_inspector, after_inspector, "npc_a")
        assert "goals" in diff["changed_fields"]
        assert diff["field_diffs"]["goals"]["added"] == ["expand territory"]
        assert diff["field_diffs"]["goals"]["removed"] == []

    def test_none_inspectors(self):
        from app.rpg.creator.world_snapshot import compute_entity_history_diff
        result = compute_entity_history_diff(None, None, "npc_ghost")
        assert result["exists_before"] is False
        assert result["exists_after"] is False


# ===========================================================================
# Determinism / stability tests
# ===========================================================================


class TestDeterminism:
    """Ensure diff output is stable with ordering noise."""

    def test_node_order_does_not_affect_diff(self):
        from app.rpg.creator.world_snapshot import compute_graph_diff
        nodes = [
            {"id": "a", "type": "npc", "label": "A", "meta": {}},
            {"id": "b", "type": "npc", "label": "B", "meta": {}},
        ]
        before = {"nodes": nodes, "edges": []}
        after = {"nodes": list(reversed(nodes)), "edges": []}
        diff = compute_graph_diff(before, after)
        assert diff["nodes"]["added"] == []
        assert diff["nodes"]["removed"] == []
        assert diff["nodes"]["changed"] == []

    def test_edge_order_does_not_affect_diff(self):
        from app.rpg.creator.world_snapshot import compute_graph_diff
        edges = [
            {"source": "a", "target": "b", "type": "x"},
            {"source": "c", "target": "d", "type": "y"},
        ]
        before = {"nodes": [], "edges": edges}
        after = {"nodes": [], "edges": list(reversed(edges))}
        diff = compute_graph_diff(before, after)
        assert diff["edges"]["added"] == []
        assert diff["edges"]["removed"] == []

    def test_meta_list_order_ignored(self):
        """Reordering list values in meta should not trigger change."""
        from app.rpg.creator.world_snapshot import compute_graph_diff
        before = {"nodes": [{"id": "a", "type": "npc", "label": "A", "meta": {"goals": ["x", "y"]}}], "edges": []}
        after = {"nodes": [{"id": "a", "type": "npc", "label": "A", "meta": {"goals": ["y", "x"]}}], "edges": []}
        diff = compute_graph_diff(before, after)
        assert diff["nodes"]["changed"] == []

    def test_changing_tags_only_changes_meta_not_identity(self):
        """Changing location tags only marks meta changed, not type or label."""
        from app.rpg.creator.world_snapshot import build_world_snapshot, compute_graph_diff
        before = build_world_snapshot(_base_setup())
        after = build_world_snapshot(_modified_setup())
        diff = compute_graph_diff(before["graph"], after["graph"])
        for c in diff["nodes"]["changed"]:
            if c["id"] == "loc_night_market":
                assert "meta" in c["fields"]
                assert "type" not in c["fields"]
                assert "label" not in c["fields"]
                break


# ===========================================================================
# Service layer
# ===========================================================================


class TestServiceInspectWorldSnapshot:
    """Tests for adventure_builder_service.inspect_world_snapshot()."""

    def test_returns_success(self):
        from app.rpg.services.adventure_builder_service import inspect_world_snapshot
        result = inspect_world_snapshot(_base_setup())
        assert result["success"] is True

    def test_returns_snapshot(self):
        from app.rpg.services.adventure_builder_service import inspect_world_snapshot
        result = inspect_world_snapshot(_base_setup(), label="Test")
        assert "snapshot" in result
        assert result["snapshot"]["label"] == "Test"

    def test_with_none_payload(self):
        from app.rpg.services.adventure_builder_service import inspect_world_snapshot
        result = inspect_world_snapshot(None)
        assert result["success"] is True

    def test_with_empty_payload(self):
        from app.rpg.services.adventure_builder_service import inspect_world_snapshot
        result = inspect_world_snapshot({})
        assert result["success"] is True


class TestServiceCompareWorld:
    """Tests for adventure_builder_service.compare_world()."""

    def test_returns_success(self):
        from app.rpg.services.adventure_builder_service import compare_world
        result = compare_world(_base_setup(), _modified_setup())
        assert result["success"] is True

    def test_returns_diff(self):
        from app.rpg.services.adventure_builder_service import compare_world
        result = compare_world(_base_setup(), _modified_setup())
        assert "diff" in result
        assert "nodes" in result["diff"]
        assert "edges" in result["diff"]
        assert "summary" in result["diff"]

    def test_returns_snapshot_ids(self):
        from app.rpg.services.adventure_builder_service import compare_world
        result = compare_world(_base_setup(), _modified_setup())
        assert "before_snapshot_id" in result
        assert "after_snapshot_id" in result

    def test_identical_payloads_no_diff(self):
        from app.rpg.services.adventure_builder_service import compare_world
        result = compare_world(_base_setup(), _base_setup())
        assert result["diff"]["nodes"]["added"] == []
        assert result["diff"]["nodes"]["removed"] == []
        assert result["diff"]["nodes"]["changed"] == []


class TestServiceCompareWorldEntity:
    """Tests for adventure_builder_service.compare_world_entity()."""

    def test_returns_success(self):
        from app.rpg.services.adventure_builder_service import compare_world_entity
        result = compare_world_entity(_base_setup(), _modified_setup(), "npc_mara_voss")
        assert result["success"] is True

    def test_returns_entity_id(self):
        from app.rpg.services.adventure_builder_service import compare_world_entity
        result = compare_world_entity(_base_setup(), _modified_setup(), "npc_mara_voss")
        assert result["entity_id"] == "npc_mara_voss"

    def test_added_entity(self):
        from app.rpg.services.adventure_builder_service import compare_world_entity
        result = compare_world_entity(_base_setup(), _modified_setup(), "npc_new_spy")
        assert result["exists_before"] is False
        assert result["exists_after"] is True

    def test_removed_entity(self):
        from app.rpg.services.adventure_builder_service import compare_world_entity
        result = compare_world_entity(_base_setup(), _modified_setup(), "fac_merchant_guild")
        assert result["exists_before"] is True
        assert result["exists_after"] is False


# ===========================================================================
# Route layer (requires Flask test client)
# ===========================================================================


@pytest.fixture
def client():
    """Flask test client using only the creator blueprint."""
    from flask import Flask
    from app.rpg.creator_routes import creator_bp

    app = Flask(__name__)
    app.register_blueprint(creator_bp)
    with app.test_client() as c:
        yield c


class TestRouteInspectWorldSnapshot:
    """POST /api/rpg/adventure/inspect-world-snapshot"""

    def test_success(self, client):
        resp = client.post(
            "/api/rpg/adventure/inspect-world-snapshot",
            json={"setup": _base_setup(), "label": "Test Snap"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["snapshot"]["label"] == "Test Snap"

    def test_missing_body(self, client):
        resp = client.post(
            "/api/rpg/adventure/inspect-world-snapshot",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_empty_setup(self, client):
        resp = client.post(
            "/api/rpg/adventure/inspect-world-snapshot",
            json={"setup": {}},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True


class TestRouteCompareWorld:
    """POST /api/rpg/adventure/compare-world"""

    def test_success(self, client):
        resp = client.post(
            "/api/rpg/adventure/compare-world",
            json={"before_setup": _base_setup(), "after_setup": _modified_setup()},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "diff" in data

    def test_missing_before(self, client):
        resp = client.post(
            "/api/rpg/adventure/compare-world",
            json={"after_setup": _modified_setup()},
        )
        assert resp.status_code == 400

    def test_missing_after(self, client):
        resp = client.post(
            "/api/rpg/adventure/compare-world",
            json={"before_setup": _base_setup()},
        )
        assert resp.status_code == 400

    def test_missing_body(self, client):
        resp = client.post(
            "/api/rpg/adventure/compare-world",
            content_type="application/json",
        )
        assert resp.status_code == 400


class TestRouteCompareEntity:
    """POST /api/rpg/adventure/compare-entity"""

    def test_success(self, client):
        resp = client.post(
            "/api/rpg/adventure/compare-entity",
            json={
                "before_setup": _base_setup(),
                "after_setup": _modified_setup(),
                "entity_id": "npc_mara_voss",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["entity_id"] == "npc_mara_voss"

    def test_missing_entity_id(self, client):
        resp = client.post(
            "/api/rpg/adventure/compare-entity",
            json={"before_setup": _base_setup(), "after_setup": _modified_setup()},
        )
        assert resp.status_code == 400

    def test_missing_setups(self, client):
        resp = client.post(
            "/api/rpg/adventure/compare-entity",
            json={"entity_id": "npc_mara_voss"},
        )
        assert resp.status_code == 400

    def test_missing_body(self, client):
        resp = client.post(
            "/api/rpg/adventure/compare-entity",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_nonexistent_entity(self, client):
        resp = client.post(
            "/api/rpg/adventure/compare-entity",
            json={
                "before_setup": _base_setup(),
                "after_setup": _modified_setup(),
                "entity_id": "npc_ghost",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["exists_before"] is False
        assert data["exists_after"] is False
