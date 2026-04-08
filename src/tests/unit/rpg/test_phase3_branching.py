"""Unit tests for PHASE 3 — BRANCHING TIMELINES + MULTIVERSE GRAPH.

Tests cover:
- TimelineNode creation and properties
- TimelineGraph DAG operations (add_event, get_branch, fork)
- Branch detection (get_forks, get_leaves, get_roots)
- EventBus timeline integration
- TimelineMetadata labeling/annotation
- create_event helper (PATCH 6)
- Edge cases: cycles, duplicates, missing events
"""

import pytest

from app.rpg.core.event_bus import Event, EventBus
from app.rpg.core.timeline_graph import TimelineGraph, TimelineNode
from app.rpg.core.timeline_metadata import TimelineMetadata

# ==================== TimelineNode Tests ====================


class TestTimelineNode:
    """Test TimelineNode creation and properties."""

    def test_node_with_parent(self):
        """Test node creation with parent_id."""
        node = TimelineNode("e1", parent_id="root")
        assert node.event_id == "e1"
        assert node.parent_id == "root"
        assert node.children == []

    def test_node_without_parent(self):
        """Test root node creation (no parent)."""
        node = TimelineNode("e1", parent_id=None)
        assert node.event_id == "e1"
        assert node.parent_id is None
        assert node.children == []

    def test_add_child(self):
        """Test adding children to a node."""
        node = TimelineNode("e1", parent_id=None)
        node.add_child("e2")
        assert "e2" in node.children

    def test_add_duplicate_child_ignored(self):
        """Test that adding same child twice doesn't duplicate."""
        node = TimelineNode("e1", parent_id=None)
        node.add_child("e2")
        node.add_child("e2")
        assert len(node.children) == 1

    def test_is_leaf_no_children(self):
        """Test is_leaf returns True for nodes without children."""
        node = TimelineNode("e1", parent_id=None)
        assert node.is_leaf() is True

    def test_is_leaf_with_children(self):
        """Test is_leaf returns False for nodes with children."""
        node = TimelineNode("e1", parent_id=None)
        node.add_child("e2")
        assert node.is_leaf() is False

    def test_is_root_no_parent(self):
        """Test is_root returns True for nodes without parent."""
        node = TimelineNode("e1", parent_id=None)
        assert node.is_root() is True

    def test_is_root_with_parent(self):
        """Test is_root returns False for nodes with parent."""
        node = TimelineNode("e1", parent_id="root")
        assert node.is_root() is False


# ==================== TimelineGraph Tests ====================


class TestTimelineGraph:
    """Test TimelineGraph DAG operations."""

    def test_empty_graph(self):
        """Test creating an empty graph."""
        graph = TimelineGraph()
        assert graph.node_count() == 0
        assert graph.get_roots() == []
        assert graph.get_leaves() == []

    def test_add_root_event(self):
        """Test adding a root event (no parent)."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        assert graph.has_event("e1")
        assert "e1" in graph.get_roots()

    def test_add_child_event(self):
        """Test adding a child event."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.add_event("e2", parent_id="e1")
        assert "e2" in graph.nodes["e1"].children

    def test_get_branch_single_path(self):
        """Test getting branch for linear path."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.add_event("e2", parent_id="e1")
        graph.add_event("e3", parent_id="e2")

        branch = graph.get_branch("e3")
        assert branch == ["e1", "e2", "e3"]

    def test_get_branch_root(self):
        """Test getting branch for root event."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        branch = graph.get_branch("e1")
        assert branch == ["e1"]

    def test_get_branch_missing_event_raises(self):
        """Test that missing event raises KeyError."""
        graph = TimelineGraph()
        with pytest.raises(KeyError, match="not found"):
            graph.get_branch("nonexistent")

    def test_fork_valid_event(self):
        """Test forking from valid event."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        result = graph.fork("e1")
        assert result == "e1"

    def test_fork_missing_event_raises(self):
        """Test that forking from missing event raises ValueError."""
        graph = TimelineGraph()
        with pytest.raises(ValueError, match="not found"):
            graph.fork("nonexistent")

    def test_get_forks_no_branches(self):
        """Test get_forks returns empty when no branching."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.add_event("e2", parent_id="e1")
        assert graph.get_forks() == {}

    def test_get_forks_with_branch(self):
        """Test get_forks detects branch points."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.add_event("e2", parent_id="e1")
        graph.add_event("e3a", parent_id="e2")
        graph.add_event("e3b", parent_id="e2")

        forks = graph.get_forks()
        assert "e2" in forks
        assert set(forks["e2"]) == {"e3a", "e3b"}

    def test_get_leaves(self):
        """Test get_leaves returns terminal events."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.add_event("e2a", parent_id="e1")
        graph.add_event("e2b", parent_id="e1")

        leaves = graph.get_leaves()
        assert set(leaves) == {"e2a", "e2b"}

    def test_get_roots(self):
        """Test get_roots returns events without parents."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.add_event("e2", parent_id=None)
        graph.add_event("e3", parent_id="e1")

        roots = graph.get_roots()
        assert set(roots) == {"e1", "e2"}

    def test_add_event_idempotent(self):
        """Test that adding same event twice doesn't duplicate."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.add_event("e1", parent_id=None)
        assert graph.node_count() == 1

    def test_add_event_cycle_guard(self):
        """Test that self-loop is prevented."""
        graph = TimelineGraph()
        with pytest.raises(ValueError, match="cycle"):
            graph.add_event("e1", parent_id="e1")

    def test_auto_create_parent_stub(self):
        """Test that adding child auto-creates parent stub if missing."""
        graph = TimelineGraph()
        graph.add_event("e2", parent_id="e1")
        assert graph.has_event("e1")
        assert graph.has_event("e2")

    def test_clear(self):
        """Test clearing the graph."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        graph.add_event("e2", parent_id="e1")
        graph.clear()
        assert graph.node_count() == 0
        assert graph.get_roots() == []

    def test_multiverse_dag_structure(self):
        """Test full multiverse DAG structure."""
        graph = TimelineGraph()
        # Build: e1 -> e2 -> [e3a, e3b] -> [e4a, e4b]
        graph.add_event("e1", parent_id=None)
        graph.add_event("e2", parent_id="e1")
        graph.add_event("e3a", parent_id="e2")
        graph.add_event("e3b", parent_id="e2")
        graph.add_event("e4a", parent_id="e3a")
        graph.add_event("e4b", parent_id="e3b")

        assert graph.node_count() == 6

        branch_a = graph.get_branch("e4a")
        assert branch_a == ["e1", "e2", "e3a", "e4a"]

        branch_b = graph.get_branch("e4b")
        assert branch_b == ["e1", "e2", "e3b", "e4b"]

        forks = graph.get_forks()
        assert "e2" in forks
        assert len(forks["e2"]) == 2  # e3a, e3b


# ==================== TimelineMetadata Tests ====================


class TestTimelineMetadata:
    """Test TimelineMetadata labeling and annotation."""

    def test_initial_state(self):
        """Test empty metadata store."""
        meta = TimelineMetadata()
        assert meta.get_all_labels() == {}
        assert meta.get_all_notes() == {}

    def test_label_and_get(self):
        """Test labeling and retrieving."""
        meta = TimelineMetadata()
        meta.label("e1", "Player arrives")
        assert meta.get_label("e1") == "Player arrives"

    def test_annotate_and_get(self):
        """Test annotating and retrieving."""
        meta = TimelineMetadata()
        meta.annotate("e1", "Critical decision point")
        assert meta.get_note("e1") == "Critical decision point"

    def test_has_label(self):
        """Test has_label check."""
        meta = TimelineMetadata()
        meta.label("e1", "test")
        assert meta.has_label("e1") is True
        assert meta.has_label("e2") is False

    def test_has_note(self):
        """Test has_note check."""
        meta = TimelineMetadata()
        meta.annotate("e1", "test")
        assert meta.has_note("e1") is True
        assert meta.has_note("e2") is False

    def test_clear(self):
        """Test clearing metadata."""
        meta = TimelineMetadata()
        meta.label("e1", "test")
        meta.annotate("e1", "note")
        meta.clear()
        assert meta.get_all_labels() == {}
        assert meta.get_all_notes() == {}

    def test_get_returns_none_for_missing(self):
        """Test that get returns None for missing events."""
        meta = TimelineMetadata()
        assert meta.get_label("nonexistent") is None
        assert meta.get_note("nonexistent") is None


# ==================== EventBus Timeline Integration Tests ====================


class TestEventBusTimelineIntegration:
    """Test EventBus timeline graph integration."""

    def test_events_added_to_timeline(self):
        """Test that emit adds events to timeline graph."""
        bus = EventBus()
        event = Event("test", payload={"tick": 1}, source="test")
        bus.emit(event)
        assert bus.timeline.has_event(event.event_id)

    def test_timeline_parent_linking(self):
        """Test that parent_id is tracked in timeline."""
        bus = EventBus()
        e1 = Event("start", payload={"tick": 1}, source="test", parent_id=None)
        bus.emit(e1)

        e2 = Event("action", payload={"tick": 2}, source="test", parent_id=e1.event_id)
        bus.emit(e2)

        branch = bus.timeline.get_branch(e2.event_id)
        assert e1.event_id in branch
        assert e2.event_id in branch

    def test_timeline_reset(self):
        """Test that reset clears timeline graph."""
        bus = EventBus()
        bus.emit(Event("test", {}, source="test"))
        assert bus.timeline.node_count() == 1

        bus.reset()
        assert bus.timeline.node_count() == 0

    def test_create_event_helper(self):
        """Test EventBus.create_event() helper."""
        bus = EventBus()
        event = bus.create_event(
            type="player_action",
            payload={"action": "look"},
            source="player",
            parent_id="e0",
        )
        assert event.type == "player_action"
        assert event.payload["action"] == "look"
        assert event.source == "player"
        assert event.parent_id == "e0"


# ==================== Edge Cases ====================


class TestEdgeCases:
    """Test edge cases for PHASE 3."""

    def test_graph_repr(self):
        """Test graph repr."""
        graph = TimelineGraph()
        graph.add_event("e1", parent_id=None)
        repr_str = repr(graph)
        assert "TimelineGraph" in repr_str
        assert "1" in repr_str  # node count

    def test_metadata_repr(self):
        """Test metadata repr."""
        meta = TimelineMetadata()
        meta.label("e1", "test")
        repr_str = repr(meta)
        assert "TimelineMetadata" in repr_str
        assert "1" in repr_str  # label count

    def test_node_repr(self):
        """Test node repr."""
        node = TimelineNode("e1", parent_id=None)
        assert "TimelineNode" in repr(node)
        assert "e1" in repr(node)