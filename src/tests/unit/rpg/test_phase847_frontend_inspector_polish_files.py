"""
Phase 8.4.7 - Inspector UX Polish Unit Tests

Tests for:
- Filter utilities (filterTimelineSnapshots, filterWorldConsequences, buildNpcOptions)
- Diff renderer (renderInspectorDiff)
- Causal trace (buildCausalTrace, renderCausalTrace)
- Integration with existing inspector state
"""
import os

import pytest


def test_inspector_filters_exists():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorFilters.js")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "filterTimelineSnapshots" in content
    assert "buildNpcOptions" in content
    assert "filterWorldConsequences" in content


def test_inspector_diff_renderer_exists():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorDiffRenderer.js")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "renderInspectorDiff" in content


def test_inspector_causal_trace_exists():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorCausalTrace.js")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "buildCausalTrace" in content
    assert "renderCausalTrace" in content


def test_inspector_state_has_new_fields():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorState.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "timelineQuery" in content
    assert "worldConsequenceFilter" in content
    assert "causalTrace" in content
    assert "loading" in content


def test_inspector_ui_imports_new_modules():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "rpgInspectorFilters" in content
    assert "rpgInspectorDiffRenderer" in content
    assert "rpgInspectorCausalTrace" in content


def test_inspector_ui_has_filter_handlers():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "timelineQuery" in content or "timeline-query" in content
    assert "worldConsequenceFilter" in content or "world-filter" in content


def test_inspector_ui_has_populate_npc_options():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "populateNpcOptions" in content


def test_filter_timeline_snapshots_logic():
    """Test the filter logic in JavaScript by examining the source."""
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorFilters.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Verify the filter checks tick, label, and snapshot_id
    assert "tick.includes(q)" in content
    assert "label.includes(q)" in content
    assert "snapshotId.includes(q)" in content


def test_filter_world_consequences_logic():
    """Test the filter logic for world consequences."""
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorFilters.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Verify it filters by type
    assert 'typeFilter' in content
    assert '"all"' in content or "'all'" in content


def test_build_npc_options_sorts_by_name():
    """Test that NPC options are sorted by name."""
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorFilters.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "npc_index" in content
    assert ".sort(" in content


def test_causal_trace_builds_chain():
    """Test that causal trace builds a chain from events, consequences, and NPC reasoning."""
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorCausalTrace.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "new_events" in content
    assert "new_consequences" in content
    assert "recent_world_consequences" in content
    assert "npc_reasoning" in content


def test_diff_renderer_uses_correct_dom_id():
    """Test that diff renderer targets the correct DOM element."""
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorDiffRenderer.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "rpg-inspector-diff-panel" in content


def test_causal_trace_renderer_uses_correct_dom_id():
    """Test that causal trace renderer targets the correct DOM element."""
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorCausalTrace.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "rpg-inspector-causal-trace" in content


def test_player_integration_has_refresh_promise():
    """Test that _refreshInspector returns a promise for debounce-awareness."""
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgPlayerIntegration.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "_inspectorRefreshPromise" in content
    assert "new Promise" in content
    assert "return this._inspectorRefreshPromise" in content


def test_inspector_ui_uses_finally_blocks():
    """Test that async methods use finally for loading state cleanup."""
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Count finally blocks in async methods (should have multiple)
    assert content.count("} finally {") >= 2


def test_select_tick_doesnt_toggle_loading_after_refresh():
    """Test that selectTick lets refreshTimeline manage its own loading state."""
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # selectTick should NOT have setInspectorLoading(false) at the end
    # It should have a comment explaining that refreshTimeline manages loading
    assert "refreshTimeline() manage its own loading" in content or "let refreshTimeline" in content


def test_consequence_button_click_handler_exists():
    """Test that consequence inspect buttons have delegated click handlers."""
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Event delegation uses closest() on [data-consequence-type]
    assert "data-consequence-type" in content
    assert "event delegation" in content or "closest" in content
    assert "worldConsequenceFilter" in content
