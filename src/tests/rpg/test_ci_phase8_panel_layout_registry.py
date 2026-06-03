from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "src" / "static" / "rpg" / "rpgPanelLayoutRegistry.js"
CHROME = ROOT / "src" / "static" / "rpg" / "rpgPanelChrome.js"
SETTINGS = ROOT / "src" / "static" / "rpg-conversation-settings.js"
RECENT_ACTIVITY = ROOT / "src" / "static" / "rpg" / "rpgRecentActivityPanel.js"
WORKFLOW = ROOT / ".github" / "workflows" / "rpg-pr-deterministic.yml"


def test_panel_layout_registry_exports_ordered_slots():
    registry = REGISTRY.read_text(encoding="utf-8")
    for expected in (
        "deterministic_phase8_panel_layout_registry",
        "PANEL_ORDER",
        "conversation-settings",
        "map-location",
        "player-hud",
        "objective-journal",
        "combat-action",
        "inventory-party",
        "recent-activity",
        "suggested-actions",
        "survival-inspector",
        "window.RpgPanelLayoutRegistry",
    ):
        assert expected in registry


def test_panel_layout_registry_is_provider_free():
    registry = REGISTRY.read_text(encoding="utf-8").lower()
    for forbidden in ("fetch(", "xmlhttprequest", "provider", "llm", "apply_turn", "math.random"):
        assert forbidden not in registry


def test_panel_layout_registry_is_loaded_before_panels():
    settings = SETTINGS.read_text(encoding="utf-8")
    assert "rpgPanelLayoutRegistry.js" in settings
    assert settings.index("rpgPanelLayoutRegistry.js") < settings.index("rpgPlayerHud.js")
    assert settings.index("rpgPanelLayoutRegistry.js") < settings.index("rpgSuggestedActionsPanel.js")


def test_panel_chrome_exports_read_only_visibility_helpers():
    chrome = CHROME.read_text(encoding="utf-8")
    for expected in (
        "deterministic_phase8_panel_chrome",
        "panelSourceBadge",
        "panelEmptyState",
        "runtimeValidationNotice",
        "attachPanelToLayout",
        "decoratePanel",
        "window.RpgPanelChrome",
    ):
        assert expected in chrome


def test_panel_chrome_is_provider_free_and_non_mutating():
    chrome = CHROME.read_text(encoding="utf-8").lower()
    for forbidden in (
        "fetch(",
        "xmlhttprequest",
        "provider",
        "llm",
        "apply_turn",
        "sendcommand",
        "executecommand",
        "math.random",
    ):
        assert forbidden not in chrome


def test_panel_chrome_loads_after_layout_registry_before_panels():
    settings = SETTINGS.read_text(encoding="utf-8")
    assert "rpgPanelChrome.js" in settings
    assert "ensurePanelChromeScript" in settings
    assert settings.index("rpgPanelLayoutRegistry.js") < settings.index("rpgPanelChrome.js")
    assert settings.index("rpgPanelChrome.js") < settings.index("rpgRecentActivityPanel.js")
    assert settings.index("rpgPanelChrome.js") < settings.index("rpgSuggestedActionsPanel.js")


def test_recent_activity_uses_panel_chrome_without_runtime_authority():
    recent = RECENT_ACTIVITY.read_text(encoding="utf-8")
    for expected in (
        "window.RpgPanelChrome",
        "panelSourceBadge",
        "panelEmptyState",
        "runtimeValidationNotice",
        "decoratePanel(target, \"recent-activity\", source)",
        "data-panel-chrome=\"deterministic_phase8_panel_chrome\"",
    ):
        assert expected in recent
    assert "commands still go through runtime validation" in recent


def test_panel_layout_registry_gate_is_ordered():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    gate = "RPG CI Phase 8 panel layout registry gate"
    assert gate in workflow
    assert "test_ci_phase8_panel_layout_registry.py" in workflow
    assert workflow.index("RPG CI Phase 8 suggested actions panel gate") < workflow.index(gate)
    assert workflow.index(gate) < workflow.index("RPG CI runtime facade manifest gate")
