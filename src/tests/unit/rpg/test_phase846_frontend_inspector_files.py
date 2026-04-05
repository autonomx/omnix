"""
Phase 8.4.6 — Frontend Inspector Files Unit Tests

Verifies that all inspector frontend files exist and contain the expected exports.
"""
import os


def test_inspector_client_exists():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorClient.js")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "class RPGInspectorClient" in content


def test_inspector_state_exists():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorState.js")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "rpgInspectorState" in content
    assert "resetInspectorState" in content


def test_inspector_renderer_exists():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorRenderer.js")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "renderTimelinePanel" in content
    assert "renderNpcReasoning" in content
    assert "renderGmAudit" in content
    assert "renderTickView" in content


def test_inspector_ui_exists():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorUI.js")
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "class RPGInspectorUI" in content


def test_inspector_client_has_expected_methods():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorClient.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "getTimeline" in content
    assert "getTimelineTick" in content
    assert "getTickDiff" in content
    assert "getNpcReasoning" in content
    assert "forceNpcGoal" in content
    assert "forceFactionTrend" in content
    assert "addDebugNote" in content


def test_inspector_ui_has_expected_methods():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorUI.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "refreshTimeline" in content
    assert "selectTick" in content
    assert "inspectNpc" in content
    assert "forceNpcGoal" in content
    assert "forceFactionTrend" in content
    assert "addDebugNote" in content
    assert "refreshAudit" in content
    assert "toggleOpen" in content


def test_inspector_renderer_has_helpers():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgInspectorRenderer.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "function esc(" in content
    assert "function safeArray(" in content
    assert "function safeObj(" in content


def test_player_integration_has_inspector_hooks():
    path = os.path.join(os.path.dirname(__file__), "../../../static/rpg/rpgPlayerIntegration.js")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "RPGInspectorUI" in content
    assert "inspectorUI" in content
    assert "ensureInspector" in content
    assert "_refreshInspector" in content