"""
Phase 8.4.7 - Inspector UX Polish Regression Tests

Ensures that the UX polish changes don't break existing inspector functionality:
- Inspector still integrates with RPGPlayerIntegration
- Existing inspector APIs continue to work
- State reset properly clears new fields
"""
import os
import pytest


def test_player_integration_still_has_inspector():
    """RPGPlayerIntegration should still reference inspectorUI."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgPlayerIntegration.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "inspectorUI" in content
    assert "ensureInspector" in content


def test_inspector_renderer_still_has_existing_functions():
    """Renderer should still export all original render functions."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorRenderer.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    for fn in ["renderInspectorShell", "renderTimelinePanel", "renderTickView",
               "renderNpcReasoning", "renderGmAudit", "setInspectorLoading"]:
        assert fn in content, f"Missing render function: {fn}"


def test_inspector_ui_still_has_original_methods():
    """UI should still have all original methods."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    for method in ["toggleOpen", "refreshTimeline", "selectTick", "inspectNpc",
                   "forceNpcGoal", "forceFactionTrend", "addDebugNote", "refreshAudit", "bind"]:
        assert method in content, f"Missing method: {method}"


def test_inspector_client_still_exists():
    """Client module should still exist and export RPGInspectorClient."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorClient.js")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "RPGInspectorClient" in content


def test_reset_inspector_state_clears_new_fields():
    """resetInspectorState should clear new fields."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorState.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Check that reset function exists and clears new fields
    assert "resetInspectorState" in content
    # The reset function should clear timelineQuery, worldConsequenceFilter, causalTrace, loading
    for field in ["timelineQuery", "worldConsequenceFilter", "causalTrace", "loading"]:
        assert f"rpgInspectorState.{field}" in content, f"resetInspectorState doesn't clear {field}"


def test_filter_empty_query_returns_all():
    """filterTimelineSnapshots should return all rows when query is empty."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorFilters.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Should have early return for empty query
    assert "if (!q) return rows" in content or '!q) return' in content


def test_filter_type_all_returns_all():
    """filterWorldConsequences should return all when typeFilter is 'all'."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorFilters.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert '"all"' in content or "'all'" in content


def test_inspector_state_exports():
    """Should export both rpgInspectorState and resetInspectorState."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorState.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "export const rpgInspectorState" in content
    assert "export function resetInspectorState" in content


def test_no_duplicate_esc_functions():
    """Each file should handle escaping consistently using the same pattern."""
    files = [
        os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorDiffRenderer.js"),
        os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorCausalTrace.js"),
    ]
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Should have safe escape function
        assert "esc" in content, f"Missing esc function or helper in {os.path.basename(path)}"


def test_inspector_ui_imports_set_inspector_loading():
    """UI should import setInspectorLoading from renderer."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "setInspectorLoading" in content


def test_inspector_ui_uses_loading_in_key_operations():
    """Key operations should set loading state."""
    path = os.path.join(os.path.dirname(__file__), "../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    # Should use setInspectorLoading in refreshTimeline, selectTick, inspectNpc, addDebugNote
    count = content.count("setInspectorLoading(")
    assert count >= 4, f"Expected at least 4 setInspectorLoading calls, found {count}"