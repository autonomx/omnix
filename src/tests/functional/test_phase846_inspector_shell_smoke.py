"""
Phase 8.4.6 — Inspector Shell Functional Tests
Smoke tests for the RPG inspector frontend shell.
"""
import os
import re


def _read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _find_static_dir():
    base = os.path.dirname(__file__)
    # Go up to project root: src/tests/functional -> src -> project root
    root = os.path.join(base, "../../..")  # F:/LLM/omnix
    return os.path.join(root, "src", "static", "rpg")


def test_inspector_client_has_post_method():
    static_dir = _find_static_dir()
    client_path = os.path.join(static_dir, "rpgInspectorClient.js")
    content = _read(client_path)
    # Verify the class has an async _post method
    assert "async _post(path, payload)" in content


def test_inspector_client_calls_expected_endpoints():
    static_dir = _find_static_dir()
    client_path = os.path.join(static_dir, "rpgInspectorClient.js")
    content = _read(client_path)

    # Verify core inspector API endpoints are wired up
    expected_endpoints = [
        "/api/rpg/inspect/timeline",
        "/api/rpg/inspect/timeline_tick",
        "/api/rpg/inspect/tick_diff",
        "/api/rpg/inspect/npc_reasoning",
    ]
    for endpoint in expected_endpoints:
        assert endpoint in content, f"Expected endpoint {endpoint} not found in rpgInspectorClient.js"


def test_inspector_client_has_gm_control_endpoints():
    static_dir = _find_static_dir()
    client_path = os.path.join(static_dir, "rpgInspectorClient.js")
    content = _read(client_path)

    gm_endpoints = [
        "/api/rpg/gm/force_npc_goal",
        "/api/rpg/gm/force_faction_trend",
        "/api/rpg/gm/debug_note",
    ]
    for endpoint in gm_endpoints:
        assert endpoint in content, f"Expected GM endpoint {endpoint} not found in rpgInspectorClient.js"


def test_inspector_renderer_escapes_html():
    static_dir = _find_static_dir()
    renderer_path = os.path.join(static_dir, "rpgInspectorRenderer.js")
    content = _read(renderer_path)

    # HTML escaping function should be present
    assert "function esc(" in content
    assert "replace" in content or "replaceAll" in content


def test_inspector_renderer_exports_shell():
    static_dir = _find_static_dir()
    renderer_path = os.path.join(static_dir, "rpgInspectorRenderer.js")
    content = _read(renderer_path)

    assert "export function renderInspectorShell" in content
    assert "export function renderTimelinePanel" in content
    assert "export function renderTickView" in content
    assert "export function renderNpcReasoning" in content
    assert "export function renderGmAudit" in content


def test_inspector_ui_initializes_with_callbacks():
    static_dir = _find_static_dir()
    ui_path = os.path.join(static_dir, "rpgInspectorUI.js")
    content = _read(ui_path)

    # Verify constructor signature has getSetupPayload and getSimulationState
    assert "constructor(getSetupPayload, getSimulationState)" in content, (
        "RPGInspectorUI constructor should accept getSetupPayload and getSimulationState callbacks"
    )


def test_inspector_ui_binds_button_handlers():
    static_dir = _find_static_dir()
    ui_path = os.path.join(static_dir, "rpgInspectorUI.js")
    content = _read(ui_path)

    expected_button_ids = [
        "rpg-inspector-toggle-btn",
        "rpg-inspector-refresh-btn",
        "rpg-inspector-inspect-npc-btn",
        "rpg-inspector-force-goal-btn",
        "rpg-inspector-force-faction-btn",
        "rpg-inspector-add-note-btn",
    ]
    for btn_id in expected_button_ids:
        assert btn_id in content, f"Expected button ID {btn_id} not found in rpgInspectorUI.js"


def test_player_integration_imports_inspector():
    static_dir = _find_static_dir()
    integration_path = os.path.join(static_dir, "rpgPlayerIntegration.js")
    content = _read(integration_path)

    assert 'import { RPGInspectorUI } from "./rpgInspectorUI.js"' in content


def test_player_integration_has_refresh_inspector_calls():
    static_dir = _find_static_dir()
    integration_path = os.path.join(static_dir, "rpgPlayerIntegration.js")
    content = _read(integration_path)

    # Verify that dialogue and state methods call refresh
    refresh_pattern = re.compile(r"await\s+this\._refreshInspector\(\)")
    matches = refresh_pattern.findall(content)
    # At least one call (enterDialogue, exitDialogue, startDialogue, etc.)
    assert len(matches) >= 3, (
        f"Expected at least 3 calls to _refreshInspector, found {len(matches)}"
    )