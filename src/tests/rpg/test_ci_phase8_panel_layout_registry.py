from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REGISTRY = ROOT / "src" / "static" / "rpg" / "rpgPanelLayoutRegistry.js"
SETTINGS = ROOT / "src" / "static" / "rpg-conversation-settings.js"
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


def test_panel_layout_registry_gate_is_ordered():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    gate = "RPG CI Phase 8 panel layout registry gate"
    assert gate in workflow
    assert "test_ci_phase8_panel_layout_registry.py" in workflow
    assert workflow.index("RPG CI Phase 8 suggested actions panel gate") < workflow.index(gate)
    assert workflow.index(gate) < workflow.index("RPG CI runtime facade manifest gate")
