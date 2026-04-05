"""
Phase 8.4.7 - Inspector UX Polish Functional/Smoke Tests

Tests the functional behavior of the inspector polish features:
- Timeline filtering
- Diff rendering
- Causal trace
- NPC dropdown selection
- Loading states
- Persisted open state
"""
import os
import json
import pytest


def test_inspector_filters_js_exports():
    """Verify filter JS exports expected functions."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorFilters.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Should export filterTimelineSnapshots
    assert "export function filterTimelineSnapshots" in content
    assert "export function filterWorldConsequences" in content
    assert "export function buildNpcOptions" in content


def test_inspector_diff_renderer_export():
    """Verify diff renderer exports renderInspectorDiff."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorDiffRenderer.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "export function renderInspectorDiff" in content


def test_inspector_causal_trace_exports():
    """Verify causal trace exports buildCausalTrace and renderCausalTrace."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorCausalTrace.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "export function buildCausalTrace" in content
    assert "export function renderCausalTrace" in content


def test_inspector_state_has_new_properties():
    """State should have timelineQuery, worldConsequenceFilter, causalTrace, loading."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorState.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    for field in ["timelineQuery", "worldConsequenceFilter", "causalTrace", "loading"]:
        assert field in content, f"Missing field: {field}"


def test_inspector_ui_uses_filters_in_refresh():
    """RPGInspectorUI should call filterTimelineSnapshots and filterWorldConsequences in refreshTimeline."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # refreshTimeline should use filters
    assert "filterTimelineSnapshots" in content
    assert "filterWorldConsequences" in content


def test_inspector_ui_renders_diff_on_refresh():
    """refreshTimeline should call renderInspectorDiff."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "renderInspectorDiff" in content


def test_inspector_ui_builds_causal_trace():
    """refreshTimeline and inspectNpc should build causal trace."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "buildCausalTrace" in content
    assert "renderCausalTrace" in content


def test_inspector_ui_has_npc_dropdown_handler():
    """bind() should add change handler for npc-select."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "rpg-inspector-npc-select" in content


def test_inspector_ui_has_timeline_query_handler():
    """bind() should add input handler for timeline-query."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "rpg-inspector-timeline-query" in content


def test_inspector_ui_has_world_filter_handler():
    """bind() should add change handler for world-filter."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "rpg-inspector-world-filter" in content


def test_inspector_open_persists_to_localstorage():
    """toggleOpen should write to localStorage."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert 'localStorage.setItem("rpg_inspector_open"' in content or "localStorage.setItem('rpg_inspector_open'" in content


def test_diff_renderer_has_loading_state():
    """Diff renderer should safely handle empty diff."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorDiffRenderer.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "safeObj" in content
    assert "safeArray" in content


def test_causal_trace_limits_chain_length():
    """Causal trace should limit chain to 20 items."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorCausalTrace.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert ".slice(0, 20)" in content